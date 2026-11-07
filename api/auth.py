"""Servicios de identidad y sesiones para AXION ATOMIC.

Este módulo no expone rutas por sí solo. Las rutas deben usar current_user y
authorize_project antes de acceder a cualquier recurso de un proyecto.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Cookie, Header, HTTPException, Request
from sqlalchemy import text

from api.database import engine

_passwords = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
SESSION_TTL = timedelta(hours=12)
COOKIE_NAME = "axion_session"
CSRF_COOKIE = "axion_csrf"


def _now():
    return datetime.now(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("La contraseña debe tener entre 12 y 1024 caracteres")
    return _passwords.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _passwords.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False


def create_user(email: str, password: str, display_name: str, terms_accepted_at: datetime | None = None) -> str:
    normalized = email.strip().casefold()
    if len(normalized) > 320 or "@" not in normalized:
        raise ValueError("Correo electrónico no válido")
    if not display_name.strip() or len(display_name) > 120:
        raise ValueError("Nombre visible no válido")
    user_id = secrets.token_urlsafe(24)
    now = _now()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id, email, email_normalized, password_hash, display_name, status, terms_accepted_at, created_at, updated_at)
            VALUES (:id, :email, :normalized, :password_hash, :name, 'pending_verification', :terms_accepted_at, :now, :now)
        """), {
            "id": user_id, "email": email.strip(), "normalized": normalized,
            "password_hash": hash_password(password), "name": display_name.strip(),
            "terms_accepted_at": terms_accepted_at, "now": now,
        })
    return user_id


def authenticate(email: str, password: str, user_agent: str | None = None) -> tuple[dict, str, str]:
    normalized = email.strip().casefold()
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id, email, display_name, password_hash, status
            FROM users WHERE email_normalized = :email
        """), {"email": normalized}).mappings().first()
        # El mismo trabajo de hash para emails inexistentes reduce diferencias temporales.
        if row is None:
            _passwords.hash("invalid-login-placeholder-password")
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")
        password_valid = verify_password(row["password_hash"], password)
        if row["status"] != "active" or not password_valid:
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        now = _now()
        conn.execute(text("""
            INSERT INTO user_sessions
              (id, user_id, token_hash, csrf_hash, created_at, expires_at, last_seen_at, user_agent_hash)
            VALUES (:id, :user_id, :token_hash, :csrf_hash, :now, :expires, :now, :ua_hash)
        """), {
            "id": secrets.token_urlsafe(24), "user_id": row["id"],
            "token_hash": _digest(token), "csrf_hash": _digest(csrf),
            "now": now, "expires": now + SESSION_TTL,
            "ua_hash": _digest(user_agent or "") if user_agent else None,
        })
        conn.execute(text("UPDATE users SET last_login_at = :now WHERE id = :id"),
                     {"now": now, "id": row["id"]})
    return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}, token, csrf


def current_user(axion_session: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> dict:
    if not axion_session:
        raise HTTPException(status_code=401, detail="Autenticación requerida")
    now = _now()
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT u.id, u.email, u.display_name, u.status, s.id AS session_id, s.csrf_hash
            FROM user_sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = :token_hash AND s.revoked_at IS NULL
              AND s.expires_at > :now AND u.status = 'active'
        """), {"token_hash": _digest(axion_session), "now": now}).mappings().first()
        if row is None:
            raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
        conn.execute(text("UPDATE user_sessions SET last_seen_at = :now WHERE id = :id"),
                     {"now": now, "id": row["session_id"]})
    return dict(row)


def require_csrf(
    user: dict,
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="Validación CSRF requerida")
    if not secrets.compare_digest(_digest(csrf_cookie), user["csrf_hash"]):
        raise HTTPException(status_code=403, detail="Token CSRF inválido")


def revoke_session(axion_session: str | None) -> None:
    if not axion_session:
        return
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE user_sessions SET revoked_at = :now
            WHERE token_hash = :token_hash AND revoked_at IS NULL
        """), {"now": _now(), "token_hash": _digest(axion_session)})


def authorize_project(user_id: str, project_id: str, minimum_roles: tuple[str, ...] = ("owner", "admin", "editor", "viewer")) -> str:
    with engine.connect() as conn:
        role = conn.execute(text("""
            SELECT role FROM project_memberships
            WHERE user_id = :user_id AND project_id = :project_id
        """), {"user_id": user_id, "project_id": project_id}).scalar_one_or_none()
    if role not in minimum_roles:
        # 404 avoids disclosing whether another user's project exists.
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return role


def verify_credentials(email: str, password: str) -> dict:
    """Verifica el primer factor sin crear sesión; permite exigir MFA antes de autenticar."""
    normalized = email.strip().casefold()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, email, display_name, password_hash, status
            FROM users WHERE email_normalized = :email
        """), {"email": normalized}).mappings().first()
    if row is None:
        _passwords.hash("invalid-login-placeholder-password")
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    if row["status"] != "active" or not verify_password(row["password_hash"], password):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}


def create_session(user_id: str, user_agent: str | None = None) -> tuple[str, str]:
    """Crea una sesión únicamente después de completar todos los factores requeridos."""
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    now = _now()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO user_sessions
              (id, user_id, token_hash, csrf_hash, created_at, expires_at, last_seen_at, user_agent_hash)
            VALUES (:id, :user_id, :token_hash, :csrf_hash, :now, :expires, :now, :ua_hash)
        """), {
            "id": secrets.token_urlsafe(24), "user_id": user_id,
            "token_hash": _digest(token), "csrf_hash": _digest(csrf),
            "now": now, "expires": now + SESSION_TTL,
            "ua_hash": _digest(user_agent or "") if user_agent else None,
        })
        conn.execute(text("UPDATE users SET last_login_at=:now WHERE id=:id"),
                     {"now": now, "id": user_id})
    return token, csrf
