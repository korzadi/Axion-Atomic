"""Rutas de sesión web. Permanecen cerradas por defecto hasta habilitar controles antiabuso."""
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.auth import (
    COOKIE_NAME, CSRF_COOKIE, authenticate, create_user, current_user,
    require_csrf, revoke_session,
)
from api.config import settings
from api.schemas import LoginRequest, RegisterRequest, ProjectCreateRequest
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
    # Comprobar primero el interruptor global: no revelar un 401 de sesión
    # cuando el servicio completo de autenticación está deshabilitado.
    _require_auth_feature()
    return current_user(axion_session)


def _csrf_guard(
    user=Depends(_authenticated_user),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    require_csrf(user, csrf_cookie, csrf_header)
    return user



def _enforce_rate_limit(request: Request, *, namespace: str, limit: int, window: timedelta, subject: str | None = None):
    # No confiar en X-Forwarded-For: solo usar la IP del socket hasta configurar
    # explícitamente una lista de proxies de confianza.
    client = request.client
    if client is None or not client.host:
        raise HTTPException(status_code=503, detail="No se pudo validar el origen de la solicitud")
    key = rate_limit_key(namespace, subject if subject is not None else client.host)
    try:
        decision = consume_rate_limit(engine=engine, bucket_key=key, limit=limit, window=window)
    except Exception as exc:
        # Fail closed: si el almacenamiento distribuido no está disponible,
        # no aceptar operaciones sensibles sin control antiabuso.
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
    _enforce_rate_limit(request, namespace="auth:register:ip", limit=10, window=timedelta(minutes=10))
    email = req.email.strip().casefold()
    _enforce_rate_limit(request, namespace="auth:register:account", subject=email,
                        limit=5, window=timedelta(hours=1))
    if not email_delivery_configured(settings) or not settings.oauth_public_base_url:
        raise HTTPException(status_code=503, detail="El registro por correo no está disponible temporalmente.")
    user_id = None
    try:
        user_id = create_user(req.email, req.password, req.display_name)
    except IntegrityError:
        # No revelar si una dirección ya está registrada.
        pass
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if user_id:
        try:
            issued = issue_email_verification_token(engine=engine, user_id=user_id)
            send_verification_email(settings=settings, recipient=email, token=issued.token)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="No se pudo enviar el correo. Solicita un nuevo envío más tarde.") from exc
    return {"status": "pending_verification",
            "message": "Si los datos son válidos, recibirás un correo con los pasos para activar tu cuenta."}


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    _require_auth_feature()
    _enforce_rate_limit(request, namespace="auth:login:ip", limit=30, window=timedelta(minutes=1))
    _enforce_rate_limit(request, namespace="auth:login:account", subject=req.email.strip().casefold(), limit=10, window=timedelta(minutes=5))
    user, token, csrf = authenticate(req.email, req.password, request.headers.get("user-agent"))
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
async def oauth_start(provider: str, request: Request):
    _require_auth_feature()
    if provider not in ("google", "github"):
        raise HTTPException(status_code=404, detail="Proveedor no admitido")
    _enforce_rate_limit(request, namespace="auth:oauth:start:" + provider,
                        limit=10, window=timedelta(minutes=10))
    try:
        destination, oauth_state = begin(engine, provider, settings)
        result = RedirectResponse(destination, status_code=302)
        result.set_cookie(key="axion_oauth_state", value=oauth_state, max_age=600,
                          httponly=True, secure=settings.auth_cookie_secure,
                          samesite="lax", path="/auth/oauth")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, code: str | None = None,
                         state: str | None = None, error: str | None = None,
                         browser_state: str | None = Cookie(default=None, alias="axion_oauth_state")):
    _require_auth_feature()
    if provider not in ("google", "github"):
        raise HTTPException(status_code=404, detail="Proveedor no admitido")
    if error or not code or not state or not browser_state or not secrets.compare_digest(state, browser_state):
        result = RedirectResponse("/?oauth_error=cancelled", status_code=303)
        result.delete_cookie("axion_oauth_state", path="/auth/oauth", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
        return result
    try:
        nonce = consume_state(engine, provider, state)
        profile = provider_profile(provider, code, nonce, settings)
        user = resolve_user(engine, provider, profile)
    except Exception:
        # Nunca mostrar ni registrar códigos, tokens ni respuestas del proveedor.
        result = RedirectResponse("/?oauth_error=failed", status_code=303)
        result.delete_cookie("axion_oauth_state", path="/auth/oauth", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
        return result
    import secrets
    from datetime import datetime, timezone
    from api.auth import _digest
    now = datetime.now(timezone.utc)
    session, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO user_sessions(id,user_id,token_hash,csrf_hash,created_at,expires_at,last_seen_at)
            VALUES(:id,:user_id,:token_hash,:csrf_hash,:now,:expires,:now)
        """), {"id": secrets.token_urlsafe(24), "user_id": user["id"],
               "token_hash": _digest(session), "csrf_hash": _digest(csrf),
               "now": now, "expires": now + timedelta(seconds=SESSION_MAX_AGE)})
        conn.execute(text("UPDATE users SET last_login_at=:now WHERE id=:id"),
                     {"now": now, "id": user["id"]})
    result = RedirectResponse("/?oauth=success", status_code=303)
    result.delete_cookie("axion_oauth_state", path="/auth/oauth", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
    result.set_cookie(key=COOKIE_NAME, value=session, max_age=SESSION_MAX_AGE,
                      httponly=True, secure=settings.auth_cookie_secure,
                      samesite="lax", path="/")
    result.set_cookie(key=CSRF_COOKIE, value=csrf, max_age=SESSION_MAX_AGE,
                      httponly=False, secure=settings.auth_cookie_secure,
                      samesite="lax", path="/")
    return result


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
    revoke_session(axion_session)
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=False, samesite="lax")
    return {"status": "logged_out"}


@router.get("/projects")
async def projects(user=Depends(_authenticated_user)):
    return {"items": list_user_projects(user["id"])}


@router.post("/projects", status_code=201)
async def create_project(req: ProjectCreateRequest, user=Depends(_csrf_guard)):
    try:
        project = create_owned_project_with_workspace(user["id"], req.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo preparar el espacio de trabajo del proyecto",
        ) from exc
    return {"project": project}
