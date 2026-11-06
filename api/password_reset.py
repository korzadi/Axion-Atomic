"""Recuperación segura de contraseña mediante token de un solo uso."""
from __future__ import annotations
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.engine import Engine
from api.auth import hash_password

TOKEN_TTL = timedelta(minutes=30)

@dataclass(frozen=True)
class PasswordResetToken:
    user_id: str
    token: str
    expires_at: datetime

def _now(value: datetime | None = None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now debe incluir zona horaria")
    return instant.astimezone(timezone.utc)

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()

def issue_password_reset_token(*, engine: Engine, email: str, now: datetime | None = None) -> PasswordResetToken | None:
    """Emite token solo para cuenta activa; None no distingue cuenta ausente/inactiva."""
    if not isinstance(email, str) or not email.strip() or len(email) > 320:
        return None
    instant = _now(now)
    raw = secrets.token_urlsafe(32)
    digest = _digest(raw)
    expires = instant + TOKEN_TTL
    with engine.begin() as conn:
        user = conn.execute(text("""
            SELECT id FROM users
            WHERE email_normalized=:email AND status='active'
            FOR UPDATE
        """), {"email": email.strip().casefold()}).mappings().first()
        if user is None:
            return None
        user_id = user["id"]
        conn.execute(text("""
            UPDATE password_reset_tokens SET consumed_at=:now
            WHERE user_id=:user_id AND consumed_at IS NULL
        """), {"now": instant, "user_id": user_id})
        conn.execute(text("""
            INSERT INTO password_reset_tokens (id,user_id,token_hash,created_at,expires_at)
            VALUES (CAST(:id AS UUID),:user_id,:digest,:now,:expires)
        """), {"id": str(uuid.uuid4()), "user_id": user_id, "digest": digest, "now": instant, "expires": expires})
    return PasswordResetToken(user_id=user_id, token=raw, expires_at=expires)

def consume_password_reset_token(*, engine: Engine, token: str, new_password: str, now: datetime | None = None) -> bool:
    """Actualiza contraseña y revoca sesiones en la misma transacción."""
    if not isinstance(token, str) or not 20 <= len(token) <= 256:
        return False
    try:
        digest = _digest(token)
    except UnicodeEncodeError:
        return False
    try:
        new_hash = hash_password(new_password)
    except (TypeError, ValueError):
        return False
    instant = _now(now)
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id,user_id FROM password_reset_tokens
            WHERE token_hash=:digest AND consumed_at IS NULL AND expires_at > :now
            FOR UPDATE
        """), {"digest": digest, "now": instant}).mappings().first()
        if row is None:
            return False
        updated = conn.execute(text("""
            UPDATE users SET password_hash=:password_hash, updated_at=:now
            WHERE id=:user_id AND status='active'
        """), {"password_hash": new_hash, "now": instant, "user_id": row["user_id"]})
        if updated.rowcount != 1:
            return False
        conn.execute(text("""
            UPDATE user_sessions SET revoked_at=:now
            WHERE user_id=:user_id AND revoked_at IS NULL
        """), {"now": instant, "user_id": row["user_id"]})
        consumed = conn.execute(text("""
            UPDATE password_reset_tokens SET consumed_at=:now
            WHERE id=CAST(:id AS UUID) AND consumed_at IS NULL
        """), {"id": str(row["id"]), "now": instant})
        if consumed.rowcount != 1:
            raise RuntimeError("No se pudo confirmar el consumo único del token")
    return True
