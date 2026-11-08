"""Integración PostgreSQL de la gestión administrativa de roles y estado."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from api.admin_routes import (
    _change_user_status,
    _grant_global_role,
    _revoke_global_role,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)


def _user(status="active", verified=True):
    user_id = str(uuid.uuid4())
    email = f"{user_id}@example.invalid"
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users
                (id,email,email_normalized,password_hash,display_name,status,email_verified_at)
            VALUES
                (:id,:email,:email,'test-hash','Admin test',:status,:verified_at)
        """), {
            "id": user_id,
            "email": email,
            "status": status,
            "verified_at": datetime.now(timezone.utc) if verified else None,
        })
    return user_id


def _session(user_id):
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO user_sessions
                (id,user_id,token_hash,csrf_hash,created_at,expires_at,last_seen_at)
            VALUES
                (:id,:user_id,:token_hash,:csrf_hash,:now,:expires_at,:now)
        """), {
            "id": session_id,
            "user_id": user_id,
            "token_hash": uuid.uuid4().hex + uuid.uuid4().hex,
            "csrf_hash": uuid.uuid4().hex + uuid.uuid4().hex,
            "now": now,
            "expires_at": now + timedelta(hours=1),
        })
    return session_id


def _active_roles(user_id):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT role FROM global_role_assignments
            WHERE user_id=:user_id AND revoked_at IS NULL ORDER BY role
        """), {"user_id": user_id}).scalars().all()


def _audit_actions(target_user_id):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT action FROM global_admin_audit_events
            WHERE target_user_id=:target ORDER BY created_at, id
        """), {"target": target_user_id}).scalars().all()


def test_grant_and_revoke_role_are_audited_and_idempotent():
    actor, target = _user(), _user()
    with patch("api.admin_routes.engine", engine):
        assert _grant_global_role(target, "billing_readonly", "Soporte temporal", actor)["status"] == "granted"
        with pytest.raises(HTTPException) as duplicate:
            _grant_global_role(target, "billing_readonly", "Soporte temporal", actor)
        assert duplicate.value.status_code == 409
        assert _active_roles(target) == ["billing_readonly"]
        assert _revoke_global_role(target, "billing_readonly", "Fin del soporte", actor)["status"] == "revoked"
        assert _active_roles(target) == []
    assert _audit_actions(target) == ["role.granted", "role.revoked"]


def test_revoke_last_active_platform_admin_is_rejected():
    actor = _user()
    target = _user()
    with patch("api.admin_routes.engine", engine):
        _grant_global_role(target, "platform_admin", "Administrador principal", actor)
        with pytest.raises(HTTPException) as blocked:
            _revoke_global_role(target, "platform_admin", "Intento de bloqueo", actor)
    assert blocked.value.status_code == 409
    assert _active_roles(target) == ["platform_admin"]


def test_disable_revokes_sessions_and_records_audit():
    actor, target = _user(), _user()
    session_id = _session(target)
    with patch("api.admin_routes.engine", engine):
        result = _change_user_status(target, "disabled", "Abuso confirmado", actor)
    assert result["status"] == "disabled"
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM users WHERE id=:id"), {"id": target}).scalar_one()
        revoked = conn.execute(
            text("SELECT revoked_at FROM user_sessions WHERE id=:id"), {"id": session_id}
        ).scalar_one()
    assert status == "disabled"
    assert revoked is not None
    assert _audit_actions(target) == ["user.disabled"]


def test_cannot_activate_unverified_or_disable_self():
    actor, target = _user(), _user(status="pending_verification", verified=False)
    with patch("api.admin_routes.engine", engine):
        with pytest.raises(HTTPException) as unverified:
            _change_user_status(target, "active", "Alta manual", actor)
        with pytest.raises(HTTPException) as self_disable:
            _change_user_status(actor, "disabled", "Baja propia", actor)
    assert unverified.value.status_code == 409
    assert self_disable.value.status_code == 409
