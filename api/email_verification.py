"""Tokens de verificación de correo de un solo uso; nunca expone hashes."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

TOKEN_TTL = timedelta(minutes=30)


@dataclass(frozen=True)
class EmailVerificationToken:
    user_id: str
    token: str
    expires_at: datetime


def _now(value: datetime | None = None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now debe incluir zona horaria")
    return instant.astimezone(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue_email_verification_token(
    *, engine: Engine, user_id: str, now: datetime | None = None,
) -> EmailVerificationToken:
    """Emite token aleatorio; invalida tokens abiertos anteriores en la misma transacción."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id es obligatorio")
    instant = _now(now)
    raw = secrets.token_urlsafe(32)
    digest = _token_hash(raw)
    expires = instant + TOKEN_TTL
    with engine.begin() as conn:
        user = conn.execute(text("""
            SELECT status FROM users WHERE id=:user_id FOR UPDATE
        """), {"user_id": user_id}).mappings().first()
        if user is None or user["status"] != "pending_verification":
            raise ValueError("La cuenta no admite verificación")
        conn.execute(text("""
            UPDATE email_verification_tokens
            SET consumed_at=:now
            WHERE user_id=:user_id AND consumed_at IS NULL
        """), {"now": instant, "user_id": user_id})
        conn.execute(text("""
            INSERT INTO email_verification_tokens
                (id,user_id,token_hash,created_at,expires_at)
            VALUES (CAST(:id AS UUID),:user_id,:digest,:now,:expires)
        """), {
            "id": str(uuid.uuid4()), "user_id": user_id,
            "digest": digest, "now": instant, "expires": expires,
        })
    return EmailVerificationToken(user_id=user_id, token=raw, expires_at=expires)


def consume_email_verification_token(
    *, engine: Engine, token: str, now: datetime | None = None,
) -> bool:
    """Consume atómicamente token vigente y activa exclusivamente cuenta pendiente."""
    if not isinstance(token, str) or not 20 <= len(token) <= 256:
        return False
    try:
        digest = _token_hash(token)
    except UnicodeEncodeError:
        return False
    instant = _now(now)
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id,user_id FROM email_verification_tokens
            WHERE token_hash=:digest AND consumed_at IS NULL AND expires_at > :now
            FOR UPDATE
        """), {"digest": digest, "now": instant}).mappings().first()
        if row is None:
            return False
        updated = conn.execute(text("""
            UPDATE users
            SET status='active', email_verified_at=:now, updated_at=:now
            WHERE id=:user_id AND status='pending_verification'
        """), {"user_id": row["user_id"], "now": instant})
        if updated.rowcount != 1:
            # No consumir un token si la cuenta fue deshabilitada o ya cambió de estado.
            return False
        consumed = conn.execute(text("""
            UPDATE email_verification_tokens SET consumed_at=:now
            WHERE id=CAST(:id AS UUID) AND consumed_at IS NULL
        """), {"id": str(row["id"]), "now": instant})
        if consumed.rowcount != 1:
            raise RuntimeError("No se pudo confirmar el consumo único del token")
    return True
