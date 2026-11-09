"""Pruebas PostgreSQL del cambio de contraseña con sesión activa."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

from api.auth import change_password, hash_password, verify_password  # noqa: E402

CURRENT = "Current-Password-123!"
NEW = "New-Strong-Password-456!"


def _user(status: str = "active", password: str = CURRENT) -> str:
    user_id = str(uuid.uuid4())
    email = f"{user_id}@example.invalid"
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id,email,email_normalized,password_hash,display_name,status,created_at,updated_at)
            VALUES (:id,:email,:email,:hash,'Cambio test',:status,:now,:now)
        """), {"id": user_id, "email": email, "hash": hash_password(password), "status": status, "now": now})
    return user_id


def _session(user_id: str) -> str:
    session_id = f"session-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO user_sessions
                (id,user_id,token_hash,csrf_hash,created_at,expires_at,last_seen_at)
            VALUES (:id,:user_id,:token_hash,:csrf_hash,:now,:expires,:now)
        """), {
            "id": session_id, "user_id": user_id,
            "token_hash": uuid.uuid4().hex + uuid.uuid4().hex,
            "csrf_hash": uuid.uuid4().hex + uuid.uuid4().hex,
            "now": now, "expires": now + timedelta(hours=12),
        })
    return session_id


def test_change_password_success_revokes_all_sessions_and_updates_hash():
    user_id = _user()
    _session(user_id)
    _session(user_id)

    change_password(user_id=user_id, current_password=CURRENT, new_password=NEW)

    with engine.connect() as conn:
        password_hash = conn.execute(text("SELECT password_hash FROM users WHERE id=:id"), {"id": user_id}).scalar_one()
        revoked = conn.execute(text("SELECT COUNT(*) FROM user_sessions WHERE user_id=:id AND revoked_at IS NOT NULL"), {"id": user_id}).scalar_one()
    assert verify_password(password_hash, NEW)
    assert not verify_password(password_hash, CURRENT)
    assert revoked == 2


def test_change_password_rejects_wrong_current_password():
    user_id = _user()
    session_id = _session(user_id)
    with pytest.raises(HTTPException) as caught:
        change_password(user_id=user_id, current_password="wrong-wrong-wrong", new_password=NEW)
    assert caught.value.status_code == 400
    with engine.connect() as conn:
        password_hash = conn.execute(text("SELECT password_hash FROM users WHERE id=:id"), {"id": user_id}).scalar_one()
        active = conn.execute(text("SELECT revoked_at FROM user_sessions WHERE id=:id"), {"id": session_id}).scalar_one()
    assert verify_password(password_hash, CURRENT)
    assert active is None


def test_change_password_rejects_same_password():
    user_id = _user()
    with pytest.raises(HTTPException) as caught:
        change_password(user_id=user_id, current_password=CURRENT, new_password=CURRENT)
    assert caught.value.status_code == 400


def test_change_password_rejects_inactive_account():
    user_id = _user(status="disabled")
    with pytest.raises(HTTPException) as caught:
        change_password(user_id=user_id, current_password=CURRENT, new_password=NEW)
    assert caught.value.status_code == 401
