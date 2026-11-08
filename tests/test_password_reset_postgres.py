"""Pruebas PostgreSQL de recuperación de contraseña."""
import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
from api.auth import verify_password
from api.password_reset import issue_password_reset_token, consume_password_reset_token

def _active_user():
    user_id = str(uuid.uuid4())
    email = f"{user_id}@example.invalid"
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id,email,email_normalized,password_hash,display_name,status)
            VALUES (:id,:email,:email,'old-hash','Reset test','active')
        """), {"id": user_id, "email": email})
    return user_id, email

def test_password_reset_token_is_hashed_single_use_and_updates_password():
    user_id, email = _active_user()
    issued = issue_password_reset_token(engine=engine, email=email)
    assert issued is not None
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT token_hash FROM password_reset_tokens WHERE user_id=:user_id"), {"user_id": user_id}).scalar_one()
    assert stored != issued.token
    assert consume_password_reset_token(engine=engine, token=issued.token, new_password="New-Strong-Password-123!") is True
    assert consume_password_reset_token(engine=engine, token=issued.token, new_password="Another-Strong-Password-456!") is False
    with engine.connect() as conn:
        password_hash = conn.execute(text("SELECT password_hash FROM users WHERE id=:id"), {"id": user_id}).scalar_one()
    assert verify_password(password_hash, "New-Strong-Password-123!")

def test_new_reset_token_invalidates_previous_token():
    _, email = _active_user()
    first = issue_password_reset_token(engine=engine, email=email)
    second = issue_password_reset_token(engine=engine, email=email)
    assert first is not None and second is not None
    assert consume_password_reset_token(engine=engine, token=first.token, new_password="New-Strong-Password-123!") is False
    assert consume_password_reset_token(engine=engine, token=second.token, new_password="New-Strong-Password-123!") is True

def test_expired_reset_token_cannot_change_password():
    user_id, email = _active_user()
    instant = datetime.now(timezone.utc)
    issued = issue_password_reset_token(engine=engine, email=email, now=instant - timedelta(hours=1))
    assert issued is not None
    assert consume_password_reset_token(engine=engine, token=issued.token, new_password="New-Strong-Password-123!", now=instant) is False
    with engine.connect() as conn:
        consumed = conn.execute(text("SELECT consumed_at FROM password_reset_tokens WHERE user_id=:id"), {"id": user_id}).scalar_one()
    assert consumed is None

def test_unknown_or_inactive_accounts_do_not_issue_reset_tokens():
    assert issue_password_reset_token(engine=engine, email="missing@example.invalid") is None
    user_id = str(uuid.uuid4())
    email = f"{user_id}@example.invalid"
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id,email,email_normalized,password_hash,display_name,status)
            VALUES (:id,:email,:email,'old-hash','Pending reset','pending_verification')
        """), {"id": user_id, "email": email})
    assert issue_password_reset_token(engine=engine, email=email) is None


def test_password_reset_revokes_every_active_session_atomically():
    user_id, email = _active_user()
    now = datetime.now(timezone.utc)
    session_ids = [f"reset-session-{uuid.uuid4()}" for _ in range(3)]
    with engine.begin() as conn:
        for session_id in session_ids:
            conn.execute(text("""
                INSERT INTO user_sessions
                    (id,user_id,token_hash,csrf_hash,created_at,expires_at,last_seen_at)
                VALUES (:id,:user_id,:token_hash,:csrf_hash,:now,:expires,:now)
            """), {
                "id": session_id, "user_id": user_id,
                "token_hash": uuid.uuid4().hex + uuid.uuid4().hex,
                "csrf_hash": uuid.uuid4().hex + uuid.uuid4().hex,
                "now": now, "expires": now + timedelta(hours=1),
            })
    issued = issue_password_reset_token(engine=engine, email=email)
    assert issued is not None
    assert consume_password_reset_token(
        engine=engine, token=issued.token,
        new_password="New-Strong-Password-123!",
    ) is True
    with engine.connect() as conn:
        revoked = conn.execute(text("""
            SELECT count(*) FROM user_sessions
            WHERE user_id=:user_id AND revoked_at IS NOT NULL
        """), {"user_id": user_id}).scalar_one()
    assert revoked == len(session_ids)

def test_malformed_token_and_weak_password_are_rejected():
    assert consume_password_reset_token(engine=engine, token="short", new_password="New-Strong-Password-123!") is False
    _, email = _active_user()
    issued = issue_password_reset_token(engine=engine, email=email)
    assert issued is not None
    assert consume_password_reset_token(engine=engine, token=issued.token, new_password="weak") is False
