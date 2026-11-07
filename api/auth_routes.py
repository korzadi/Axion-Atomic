"""Rutas de sesión web. Permanecen cerradas por defecto hasta habilitar controles antiabuso."""
from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from urllib.parse import quote
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.auth import (
    COOKIE_NAME, CSRF_COOKIE, authenticate, create_user, current_user,
    require_csrf, revoke_session, verify_credentials, create_session,
)
from api.config import settings
from api.schemas import (
    LoginRequest, RegisterRequest, ProjectCreateRequest,
    MfaChallengeVerifyRequest, MfaConfirmRequest, EmailTokenRequest,
    PasswordResetRequest, EmailAddressRequest,
)
from api.password_reset import issue_password_reset_token, consume_password_reset_token
from api.mfa import AesGcmTotpCipher, EnvironmentMfaKeyProvider, MfaError
from api.mfa_store import (
    begin_enrollment, confirm_enrollment, get_mfa_status, is_mfa_enabled,
    issue_login_challenge, verify_login_challenge,
)
from api.project_creation import create_owned_project_with_workspace
from api.projects import list_user_projects
from api.database import engine
from api.rate_limit import consume_rate_limit, rate_limit_key
from api.oauth import begin, consume_state, configured, provider_profile, resolve_user
from api.email_delivery import email_delivery_configured, send_verification_email
from api.email_verification import issue_email_verification_token

router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_MAX_AGE = 12 * 60 * 60


def _require_auth_feature():
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="La autenticación web aún no está habilitada")


def _authenticated_user(axion_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    _require_auth_feature()
    return current_user(axion_session)


def _csrf_guard(
    user=Depends(_authenticated_user),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    require_csrf(user, csrf_cookie, csrf_header)
    return user


def _create_oauth_session(user_id: str):
    from api.auth import _digest
    now = datetime.now(timezone.utc)
    session, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO user_sessions(id,user_id,token_hash,csrf_hash,created_at,expires_at,last_seen_at)
            VALUES(:id,:user_id,:token_hash,:csrf_hash,:now,:expires,:now)
        """), {
            "id": secrets.token_urlsafe(24), "user_id": user_id,
            "token_hash": _digest(session), "csrf_hash": _digest(csrf),
            "now": now, "expires": now + timedelta(seconds=SESSION_MAX_AGE),
        })
        conn.execute(text("UPDATE users SET last_login_at=:now WHERE id=:id"),
                     {"now": now, "id": user_id})
    return session, csrf



def _enforce_rate_limit(request: Request, *, namespace: str, limit: int, window: timedelta, subject: str | None = None):
    client = request.client
    if client is None or not client.host:
        raise HTTPException(status_code=503, detail="No se pudo validar el origen de la solicitud")
    key = rate_limit_key(namespace, subject if subject is not None else client.host)
    try:
        decision = consume_rate_limit(engine=engine, bucket_key=key, limit=limit, window=window)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Protección temporalmente no disponible") from exc
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Demasiadas solicitudes. Inténtalo más tarde.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


@router.post("/register", status_code=202)
async def register(req: RegisterRequest, request: Request):
    _require_auth_feature()
    await run_in_threadpool(_enforce_rate_limit, request, namespace="auth:register:ip", limit=10, window=timedelta(minutes=10))
    if req.terms_accepted is not True:
        raise HTTPException(status_code=400, detail="Debes aceptar los términos y la política de privacidad.")
    email = req.email.strip().casefold()
    await run_in_threadpool(_enforce_rate_limit, request, namespace="auth:register:account", subject=email,
                        limit=5, window=timedelta(hours=1))
    if not email_delivery_configured(settings) or not settings.oauth_public_base_url:
        raise HTTPException(status_code=503, detail="El registro por correo no está disponible temporalmente.")
    user_id = None
    try:
        user_id = await run_in_threadpool(create_user, req.email, req.password, req.display_name, terms_accepted_at=datetime.now(timezone.utc))
    except IntegrityError:
        pass
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if user_id:
        try:
            issued = await run_in_threadpool(issue_email_verification_token, engine=engine, user_id=user_id)
            await run_in_threadpool(send_verification_email, settings=settings, recipient=email, token=issued.token)
        except Exception:
            raise HTTPException(status_code=503, detail="No se pudo enviar el correo. Solicita un nuevo envío más tarde.") from None
    return {"status": "pending_verification",
            "message": "Si los datos son válidos, recibirás un correo con los pasos para activar tu cuenta."}


@router.post("/email/verify")
async def verify_email(req: EmailTokenRequest, request: Request, response: Response):
    """Consume un token de verificación de correo de un solo uso."""
    _require_auth_feature()
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:email:verify:ip",
        limit=20, window=timedelta(minutes=10),
    )
    from api.email_verification import consume_email_verification_token
    valid = await run_in_threadpool(
        consume_email_verification_token, engine=engine, token=req.token,
    )
    response.headers["Cache-Control"] = "no-store"
    if not valid:
        raise HTTPException(status_code=400, detail="El enlace de verificación no es válido o ha caducado.")
    return {"status": "verified", "message": "Correo verificado. Ya puedes iniciar sesión."}


@router.post("/email/resend")
async def resend_email_verification(req: EmailAddressRequest, request: Request):
    """Reenvía verificación sin revelar si la cuenta existe."""
    _require_auth_feature()
    email = req.email.strip().casefold()
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:email:resend:ip",
        limit=10, window=timedelta(minutes=10),
    )
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:email:resend:account",
        subject=email, limit=3, window=timedelta(hours=1),
    )
    if not email_delivery_configured(settings) or not settings.oauth_public_base_url:
        raise HTTPException(status_code=503, detail="El correo transaccional no está disponible temporalmente.")
    with engine.connect() as conn:
        user_id = conn.execute(text(
            "SELECT id FROM users WHERE email_normalized=:email AND status='pending_verification'"
        ), {"email": email}).scalar_one_or_none()
    if user_id:
        try:
            issued = await run_in_threadpool(issue_email_verification_token, engine=engine, user_id=str(user_id))
            await run_in_threadpool(send_verification_email, settings=settings, recipient=email, token=issued.token)
        except Exception:
            # Respuesta uniforme: no confirmar existencia ni estado de la cuenta.
            pass
    return {"status": "accepted", "message": "Si la cuenta necesita verificación, recibirás un correo."}


@router.post("/password/forgot", status_code=202)
async def password_forgot(req: EmailAddressRequest, request: Request):
    """Solicita recuperación sin revelar si el correo pertenece a una cuenta."""
    _require_auth_feature()
    email = req.email.strip().casefold()
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:password:forgot:ip",
        limit=10, window=timedelta(minutes=10),
    )
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:password:forgot:account",
        subject=email, limit=3, window=timedelta(hours=1),
    )
    if not email_delivery_configured(settings) or not settings.oauth_public_base_url:
        raise HTTPException(status_code=503, detail="El correo transaccional no está disponible temporalmente.")
    try:
        issued = await run_in_threadpool(issue_password_reset_token, engine=engine, email=email)
        if issued:
            await run_in_threadpool(send_password_reset_email, settings=settings, recipient=email, token=issued.token)
    except Exception:
        pass
    return {"status": "accepted", "message": "Si la cuenta está activa, recibirás instrucciones para recuperar el acceso."}


@router.post("/password/reset")
async def password_reset(req: PasswordResetRequest, request: Request, response: Response):
    """Cambia contraseña con token único y revoca todas las sesiones existentes."""
    _require_auth_feature()
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:password:reset:ip",
        limit=10, window=timedelta(minutes=10),
    )
    from api.password_reset import consume_password_reset_token
    valid = await run_in_threadpool(
        consume_password_reset_token, engine=engine, token=req.token,
        new_password=req.new_password,
    )
    response.headers["Cache-Control"] = "no-store"
    if not valid:
        raise HTTPException(status_code=400, detail="El enlace no es válido, ha caducado o la contraseña no cumple los requisitos.")
    return {"status": "password_updated", "message": "Contraseña actualizada. Inicia sesión nuevamente."}


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    _require_auth_feature()
    await run_in_threadpool(_enforce_rate_limit, request, namespace="auth:login:ip", limit=30, window=timedelta(minutes=1))
    await run_in_threadpool(_enforce_rate_limit, request, namespace="auth:login:account", subject=req.email.strip().casefold(), limit=10, window=timedelta(minutes=5))
    user = await run_in_threadpool(verify_credentials, req.email, req.password)
    if await run_in_threadpool(is_mfa_enabled, engine=engine, user_id=user["id"]):
        challenge = await run_in_threadpool(
            issue_login_challenge, engine=engine, user_id=user["id"], purpose="login",
        )
        return JSONResponse(
            status_code=202,
            content={"mfa_required": True, "challenge_token": challenge, "expires_in": 300},
            headers={"Cache-Control": "no-store"},
        )
    token, csrf = await run_in_threadpool(
        create_session, user_id=user["id"], user_agent=request.headers.get("user-agent"),
    )
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=SESSION_MAX_AGE, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax", path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE, value=csrf, max_age=SESSION_MAX_AGE, httponly=False,
        secure=settings.auth_cookie_secure, samesite="lax", path="/",
    )
    return {"user": user, "csrf_token": csrf, "expires_in": SESSION_MAX_AGE}



@router.get("/oauth/providers")
async def oauth_providers():
    return {"google": configured(settings, "google"), "github": configured(settings, "github")}


@router.get("/oauth/{provider}/start")
async def oauth_start(provider: str, request: Request, terms_accepted: bool = False):
    _require_auth_feature()
    if provider not in ("google", "github"):
        raise HTTPException(status_code=404, detail="Proveedor no admitido")
    await run_in_threadpool(_enforce_rate_limit, request, namespace="auth:oauth:start:" + provider,
                        limit=10, window=timedelta(minutes=10))
    try:
        destination, oauth_state = await run_in_threadpool(begin, engine, provider, settings, terms_accepted=terms_accepted)
        result = RedirectResponse(destination, status_code=302)
        result.set_cookie(key="axion_oauth_state", value=oauth_state, max_age=600,
                          httponly=True, secure=settings.auth_cookie_secure,
                          samesite="lax", path="/auth/oauth")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request, code: str | None = None,
                         state: str | None = None, error: str | None = None,
                         browser_state: str | None = Cookie(default=None, alias="axion_oauth_state")):
    _require_auth_feature()
    if provider not in ("google", "github"):
        raise HTTPException(status_code=404, detail="Proveedor no admitido")
    await run_in_threadpool(
        _enforce_rate_limit, request,
        namespace="auth:oauth:callback:" + provider,
        limit=20, window=timedelta(minutes=10),
    )
    if error or not code or not state or not browser_state or not secrets.compare_digest(state, browser_state):
        result = RedirectResponse("/?oauth_error=cancelled", status_code=303)
        result.delete_cookie("axion_oauth_state", path="/auth/oauth", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
        return result
    try:
        state_data = await run_in_threadpool(consume_state, engine, provider, state)
        if state_data["terms_accepted"] is not True:
            raise ValueError("Consentimiento legal no registrado")
        profile = await run_in_threadpool(provider_profile, provider, code, state_data["nonce"], settings)
        user = await run_in_threadpool(resolve_user, engine, provider, profile, terms_accepted=state_data["terms_accepted"])
    except Exception:
        result = RedirectResponse("/?oauth_error=failed", status_code=303)
        result.delete_cookie("axion_oauth_state", path="/auth/oauth", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
        return result
    if await run_in_threadpool(is_mfa_enabled, engine=engine, user_id=user["id"]):
        challenge = await run_in_threadpool(
            issue_login_challenge, engine=engine, user_id=user["id"], purpose="oauth",
        )
        result = RedirectResponse("/?mfa_required=1", status_code=303)
        result.headers["Cache-Control"] = "no-store"
        result.delete_cookie("axion_oauth_state", path="/auth/oauth", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
        result.set_cookie(
            key="axion_mfa_challenge", value=challenge, max_age=300, httponly=True,
            secure=settings.auth_cookie_secure, samesite="lax",
            path="/auth/mfa/challenge/verify",
        )
        return result
    session, csrf = await run_in_threadpool(create_session, user_id=user["id"])
    result = RedirectResponse("/?oauth=success", status_code=303)
    result.delete_cookie("axion_oauth_state", path="/auth/oauth", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
    result.set_cookie(key=COOKIE_NAME, value=session, max_age=SESSION_MAX_AGE,
                      httponly=True, secure=settings.auth_cookie_secure,
                      samesite="lax", path="/")
    result.set_cookie(key=CSRF_COOKIE, value=csrf, max_age=SESSION_MAX_AGE,
                      httponly=False, secure=settings.auth_cookie_secure,
                      samesite="lax", path="/")
    return result


@router.get("/mfa/status")
async def mfa_status(user=Depends(_authenticated_user)):
    return await run_in_threadpool(get_mfa_status, engine=engine, user_id=user["id"])


@router.post("/mfa/enroll")
async def mfa_enroll(request: Request, response: Response, user=Depends(_csrf_guard)):
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:mfa:enroll",
        limit=3, window=timedelta(hours=1), subject=user["id"],
    )
    try:
        cipher = AesGcmTotpCipher(EnvironmentMfaKeyProvider())
        secret = await run_in_threadpool(
            begin_enrollment, engine=engine, cipher=cipher, user_id=user["id"],
        )
    except (MfaError, ValueError) as exc:
        raise HTTPException(status_code=503 if isinstance(exc, MfaError) else 409,
                            detail="No se pudo iniciar el enrolamiento MFA.") from exc
    label = quote("AXYRON ATOMIC:" + user["email"])
    issuer = quote("AXYRON ATOMIC")
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    response.headers["Cache-Control"] = "no-store"
    return {"secret": secret, "otpauth_uri": uri, "issuer": "AXYRON ATOMIC"}


@router.post("/mfa/confirm")
async def mfa_confirm(req: MfaConfirmRequest, request: Request, response: Response, user=Depends(_csrf_guard)):
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:mfa:confirm",
        limit=10, window=timedelta(minutes=10), subject=user["id"],
    )
    try:
        cipher = AesGcmTotpCipher(EnvironmentMfaKeyProvider())
        recovery_codes = await run_in_threadpool(
            confirm_enrollment, engine=engine, cipher=cipher,
            user_id=user["id"], code=req.code,
        )
    except (MfaError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="No se pudo confirmar el código MFA.") from exc
    response.headers["Cache-Control"] = "no-store"
    return {"status": "enabled", "recovery_codes": recovery_codes}


@router.post("/mfa/challenge/verify")
async def mfa_challenge_verify(
    req: MfaChallengeVerifyRequest, request: Request, response: Response,
    oauth_challenge: str | None = Cookie(default=None, alias="axion_mfa_challenge"),
):
    _require_auth_feature()
    challenge_token = oauth_challenge or req.challenge_token
    expected_purpose = "oauth" if oauth_challenge else "login"
    if not challenge_token:
        raise HTTPException(status_code=400, detail="Desafío MFA requerido")
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:mfa:verify:ip",
        limit=20, window=timedelta(minutes=10),
    )
    from api.mfa_store import _digest as _mfa_digest
    await run_in_threadpool(
        _enforce_rate_limit, request, namespace="auth:mfa:verify:challenge",
        limit=5, window=timedelta(minutes=10), subject=_mfa_digest(challenge_token),
    )
    try:
        cipher = AesGcmTotpCipher(EnvironmentMfaKeyProvider())
        user_id = await run_in_threadpool(
            verify_login_challenge, engine=engine, cipher=cipher,
            challenge_token=challenge_token, code=req.code,
            expected_purpose=expected_purpose,
        )
    except MfaError as exc:
        raise HTTPException(status_code=503, detail="La verificación MFA no está disponible.") from exc
    if not user_id:
        raise HTTPException(status_code=401, detail="Código MFA inválido o desafío expirado.")
    token, csrf = await run_in_threadpool(
        create_session, user_id=user_id, user_agent=request.headers.get("user-agent"),
    )
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=SESSION_MAX_AGE, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax", path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE, value=csrf, max_age=SESSION_MAX_AGE, httponly=False,
        secure=settings.auth_cookie_secure, samesite="lax", path="/",
    )
    response.delete_cookie(
        "axion_mfa_challenge", path="/auth/mfa/challenge/verify",
        secure=settings.auth_cookie_secure, httponly=True, samesite="lax",
    )
    return {"status": "authenticated", "csrf_token": csrf, "expires_in": SESSION_MAX_AGE}


@router.get("/me")
async def me(user=Depends(_authenticated_user)):
    return {"user": {key: user[key] for key in ("id", "email", "display_name")}}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user=Depends(_csrf_guard),
    axion_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    await run_in_threadpool(revoke_session, axion_session)
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=False, samesite="lax")
    return {"status": "logged_out"}


@router.get("/projects")
async def projects(user=Depends(_authenticated_user)):
    return {"items": await run_in_threadpool(list_user_projects, user["id"])}


@router.post("/projects", status_code=201)
async def create_project(req: ProjectCreateRequest, request: Request, user=Depends(_csrf_guard)):
    # Evita abuso de disco y creación ilimitada de workspaces por una cuenta.
    await run_in_threadpool(
        _enforce_rate_limit, request,
        namespace="auth:projects:create:user", subject=user["id"],
        limit=10, window=timedelta(hours=1),
    )
    try:
        project = await run_in_threadpool(create_owned_project_with_workspace, user["id"], req.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo preparar el espacio de trabajo del proyecto",
        ) from exc
    return {"project": project}
