"""Rutas de sesión web. Permanecen cerradas por defecto hasta habilitar controles antiabuso."""
from datetime import timedelta
\nfrom fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from api.auth import (
    COOKIE_NAME, CSRF_COOKIE, authenticate, create_user, current_user,
    require_csrf, revoke_session,
)
from api.config import settings
from api.schemas import LoginRequest, RegisterRequest, ProjectCreateRequest
from api.project_creation import create_owned_project_with_workspace
from api.projects import list_user_projects\nfrom api.database import engine\nfrom api.rate_limit import consume_rate_limit, rate_limit_key

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
async def register(req: RegisterRequest):
    _require_auth_feature()
    try:
        create_user(req.email, req.password, req.display_name)
    except IntegrityError:
        # No revelar si una dirección ya está registrada.
        pass
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "status": "pending_verification",
        "message": "Si los datos son válidos, la cuenta permanecerá pendiente hasta verificar el correo.",
    }


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    _require_auth_feature()
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
