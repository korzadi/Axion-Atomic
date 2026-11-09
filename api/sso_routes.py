"""SSO entre la web principal y AXYRON Studio, sin ampliar cookies ni dominios.

Diseño (equivalent to PKCE, con código de un solo uso y TTL corto):

- Landing: ``POST /auth/sso/authorize`` (sesión + CSRF). Mints a one-time code
  bound to the authenticated user. Devuelve ``{studio_url}`` con ``code`` y
  ``state`` (solo se guardan hashes). El Studio nunca recibe la sesión ni las
  cookies del landing.
- Studio: ``POST /auth/sso/exchange`` (público, con rate limiting estricto).
  Intercambia el código por UNA sesión nueva, host-only (el nginx del Studio
  proxea ``/auth/*`` al mismo servicio; la cookie se limita automáticamente al
  host del Studio, sin atributo ``Domain``).
- El código es de un solo uso, caduca a los 180 s y se consume
  atómicamente; state es un nonce anti-CSRF de un solo uso por intercambio.
- Ninguna cookie, token ni sesión se mueve en URL permanente; el código es un
  secreto de un solo uso con TTL, enviado solo sobre TLS.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from api.auth import COOKIE_NAME, CSRF_COOKIE, create_session, current_user, require_csrf
from api.auth_routes import SESSION_MAX_AGE
from api.config import settings
from api.database import engine
from api.rate_limit import consume_rate_limit, rate_limit_key

router = APIRouter(prefix="/auth/sso", tags=["sso"])

SSO_TTL_SECONDS = 180
EXCHANGE_LIMIT = 5


class SsoExchangeRequest(BaseModel):
    code: str = Field(min_length=20, max_length=256)
    state: str = Field(min_length=16, max_length=256)


def _digest(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client_host(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host or None


def _limit_or_503(
    request: Request | None,
    namespace: str,
    limit: int,
    window: timedelta,
    subject: str | None = None,
) -> None:
    host = _client_host(request)
    if not host:
        raise HTTPException(status_code=503, detail="No se pudo validar el origen")
    key = rate_limit_key(namespace, subject or host)
    try:
        decision = consume_rate_limit(engine=engine, bucket_key=key, limit=limit, window=window)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Protección temporalmente no disponible") from exc
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Demasiadas solicitudes",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def _studio_origin() -> str:
    origin = getattr(settings, "studio_origin", None)
    if not origin:
        raise HTTPException(status_code=503, detail="SSO no está configurado en este despliegue")
    return origin


def authorize_sso_code(*, user_id: str, origin: str, now: datetime | None = None) -> dict:
    """Mints a single-use code bound to the user; stores only hashes."""
    if not origin.startswith("https://"):
        raise HTTPException(status_code=503, detail="SSO no está configurado en este despliegue")
    instant = (now or _now()).astimezone(timezone.utc)
    code = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    expires = instant + timedelta(seconds=SSO_TTL_SECONDS)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO sso_codes (id, user_id, code_hash, state_hash, created_at, expires_at)
            VALUES (CAST(:id AS UUID), :user_id, :code_hash, :state_hash, :now, :expires)
        """), {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "code_hash": _digest(code),
            "state_hash": _digest(state),
            "now": instant,
            "expires": expires,
        })
    callback = f"{origin}/sso/callback?code={code}&state={state}"
    return {
        "code": code,
        "state": state,
        "expires_in": SSO_TTL_SECONDS,
        "studio_url": callback,
    }


def exchange_sso_code(*, code: str, state: str, now: datetime | None = None) -> tuple[str, str]:
    """Consume a code atomically; returns a NEW (token, csrf) session pair."""
    instant = (now or _now()).astimezone(timezone.utc)
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id, user_id, state_hash, expires_at
            FROM sso_codes WHERE code_hash=:digest FOR UPDATE
        """), {"digest": _digest(code)}).mappings().first()
        if row is None:
            raise HTTPException(status_code=401, detail="Código SSO inválido")
        if row["expires_at"] <= instant:
            raise HTTPException(status_code=401, detail="Código SSO caducado")
        if secrets.compare_digest(_digest(state), row["state_hash"]) is False:
            raise HTTPException(status_code=401, detail="Estado SSO inválido")
        consumed = conn.execute(text("""
            UPDATE sso_codes SET consumed_at=:now
            WHERE id=CAST(:id AS UUID) AND consumed_at IS NULL
        """), {"now": instant, "id": str(row["id"])})
        if consumed.rowcount != 1:
            raise HTTPException(status_code=401, detail="Código SSO ya utilizado")
        user_id = str(row["user_id"])
    return create_session(user_id, user_agent=None)


@router.post("/authorize")
async def sso_authorize(
    request: Request,
    axion_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    """Mint a single-use code for the authenticated user. Requires CSRF."""
    if not getattr(settings, "auth_enabled", False):
        raise HTTPException(status_code=503, detail="La autenticación web aún no está habilitada")
    origin = _studio_origin()
    user = await run_in_threadpool(current_user, axion_session)
    require_csrf(user, csrf_cookie, csrf_header)
    _limit_or_503(request, "auth:sso:authorize:user", 20, timedelta(minutes=10), str(user["id"]))
    result = await run_in_threadpool(authorize_sso_code, user_id=str(user["id"]), origin=origin)
    return {
        "code": result["code"],
        "state": result["state"],
        "expires_in": result["expires_in"],
        "studio_url": result["studio_url"],
    }


@router.post("/exchange")
async def sso_exchange(req: SsoExchangeRequest, request: Request):
    """Exchange a single-use code for a NEW session scoped to the Studio host."""
    if not getattr(settings, "auth_enabled", False):
        raise HTTPException(status_code=503, detail="La autenticación web aún no está habilitada")
    _limit_or_503(request, "auth:sso:exchange:ip", EXCHANGE_LIMIT, timedelta(minutes=10))
    token, csrf = await run_in_threadpool(exchange_sso_code, code=req.code, state=req.state)
    response = JSONResponse({"status": "authenticated", "csrf_token": csrf, "expires_in": SESSION_MAX_AGE})
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=SESSION_MAX_AGE, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax", path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE, value=csrf, max_age=SESSION_MAX_AGE, httponly=False,
        secure=settings.auth_cookie_secure, samesite="lax", path="/",
    )
    return response
