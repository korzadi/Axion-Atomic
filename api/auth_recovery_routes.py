from datetime import timedelta
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text

from api.config import settings
from api.database import engine
from api.email_delivery import email_delivery_configured, send_password_reset_email, send_verification_email
from api.email_verification import issue_email_verification_token, consume_email_verification_token
from api.password_reset import issue_password_reset_token, consume_password_reset_token
from api.rate_limit import consume_rate_limit, rate_limit_key
from api.schemas import EmailTokenRequest, PasswordResetRequest, EmailAddressRequest

router = APIRouter(prefix="/auth", tags=["authentication-recovery"])


def _gate():
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="La autenticación web aún no está habilitada")


def _limit(request: Request, namespace: str, limit: int, window: timedelta, subject: str | None = None):
    if request.client is None or not request.client.host:
        raise HTTPException(status_code=503, detail="No se pudo validar el origen")
    key = rate_limit_key(namespace, subject or request.client.host)
    try:
        decision = consume_rate_limit(engine=engine, bucket_key=key, limit=limit, window=window)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Protección temporalmente no disponible") from exc
    if not decision.allowed:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes",
                            headers={"Retry-After": str(decision.retry_after_seconds)})


def _resend_verification_if_pending(email: str) -> None:
    with engine.connect() as conn:
        user_id = conn.execute(
            text("SELECT id FROM users WHERE email_normalized=:email AND status='pending_verification'"),
            {"email": email},
        ).scalar_one_or_none()
    if user_id:
        issued = issue_email_verification_token(engine=engine, user_id=user_id)
        send_verification_email(settings=settings, recipient=email, token=issued.token)


def _send_password_reset_if_active(email: str) -> None:
    issued = issue_password_reset_token(engine=engine, email=email)
    if issued:
        send_password_reset_email(settings=settings, recipient=email, token=issued.token)


@router.post("/verify-email")
async def verify_email(req: EmailTokenRequest, request: Request):
    _gate()
    await run_in_threadpool(_limit, request, "auth:verify-email:ip", 20, timedelta(minutes=10))
    if not await run_in_threadpool(consume_email_verification_token, engine=engine, token=req.token):
        raise HTTPException(status_code=400, detail="El enlace no es válido o ha caducado.")
    return {"status": "verified", "message": "Correo verificado. Ya puedes iniciar sesión."}


@router.post("/resend-verification", status_code=202)
async def resend_verification(req: EmailAddressRequest, request: Request):
    _gate()
    email = req.email.strip().casefold()
    await run_in_threadpool(_limit, request, "auth:verify-resend:ip", 10, timedelta(minutes=10))
    await run_in_threadpool(_limit, request, "auth:verify-resend:account", 3, timedelta(hours=1), email)
    if email_delivery_configured(settings) and settings.oauth_public_base_url:
        try:
            await run_in_threadpool(_resend_verification_if_pending, email)
        except Exception:
            pass
    return {"status": "accepted", "message": "Si existe una cuenta pendiente para ese correo, recibirás instrucciones."}


@router.post("/password/forgot", status_code=202)
async def forgot_password(req: EmailAddressRequest, request: Request):
    _gate()
    email = req.email.strip().casefold()
    await run_in_threadpool(_limit, request, "auth:password-forgot:ip", 10, timedelta(minutes=10))
    await run_in_threadpool(_limit, request, "auth:password-forgot:account", 3, timedelta(hours=1), email)
    if email_delivery_configured(settings) and settings.oauth_public_base_url:
        try:
            await run_in_threadpool(_send_password_reset_if_active, email)
        except Exception:
            pass
    return {"status": "accepted", "message": "Si existe una cuenta activa para ese correo, recibirás instrucciones."}


@router.post("/password/reset")
async def reset_password(req: PasswordResetRequest, request: Request):
    _gate()
    await run_in_threadpool(_limit, request, "auth:password-reset:ip", 10, timedelta(minutes=10))
    if not await run_in_threadpool(consume_password_reset_token, engine=engine, token=req.token, new_password=req.new_password):
        raise HTTPException(status_code=400, detail="El enlace no es válido o ha caducado.")
    return {"status": "password_changed", "message": "Contraseña actualizada. Inicia sesión nuevamente."}
