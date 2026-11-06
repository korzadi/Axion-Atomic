"""Integración PostgreSQL de tokens de verificación de correo."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

from api.email_verification import (
    consume_email_verification_token, issue_email_verification_token,
)


def _pending_user():
    user_id = str(uuid.uuid4())
    email = f"{user_id}@example.invalid"
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id,email,email_normalized,password_hash,display_name,status)
            VALUES (:id,:email,:email,'test-hash','Email test','pending_verification')
        """), {"id": user_id, "email": email})
    return user_id


def test_verification_token_is_hashed_single_use_and_activates_user():
    user_id = _pending_user()
    issued = issue_email_verification_token(engine=engine, user_id=user_id)
    with engine.connect() as conn:
        stored = conn.execute(text("""
            SELECT token_hash FROM email_verification_tokens WHERE user_id=:user_id
        """), {"user_id": user_id}).scalar_one()
        status = conn.execute(text("SELECT status FROM users WHERE id=:id"), {"id": user_id}).scalar_one()
    assert stored != issued.token
    assert status == "pending_verification"
    assert consume_email_verification_token(engine=engine, token=issued.token) is True
    assert consume_email_verification_token(engine=engine, token=issued.token) is False
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT status,email_verified_at FROM users WHERE id=:id
        """), {"id": user_id}).one()
    assert row.status == "active"
    assert row.email_verified_at is not None


def test_new_token_invalidates_previous_open_token():
    user_id = _pending_user()
    first = issue_email_verification_token(engine=engine, user_id=user_id)
    second = issue_email_verification_token(engine=engine, user_id=user_id)
    assert consume_email_verification_token(engine=engine, token=first.token) is False
    assert consume_email_verification_token(engine=engine, token=second.token) is True


def test_expired_token_cannot_activate_account():
    user_id = _pending_user()
    instant = datetime.now(timezone.utc)
    issued = issue_email_verification_token(
        engine=engine, user_id=user_id, now=instant - timedelta(hours=1)
    )
    assert consume_email_verification_token(engine=engine, token=issued.token, now=instant) is False
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM users WHERE id=:id"), {"id": user_id}).scalar_one()
    assert status == "pending_verification"


def test_disabled_account_cannot_be_activated_by_token():
    user_id = _pending_user()
    issued = issue_email_verification_token(engine=engine, user_id=user_id)
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET status='disabled' WHERE id=:id"), {"id": user_id})
    assert consume_email_verification_token(engine=engine, token=issued.token) is False
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM users WHERE id=:id"), {"id": user_id}).scalar_one()
    assert status == "disabled"


def test_malformed_tokens_are_rejected():
    assert consume_email_verification_token(engine=engine, token="short") is False
    assert consume_email_verification_token(engine=engine, token="ñ" * 30) is False
