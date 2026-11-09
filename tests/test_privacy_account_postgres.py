"""Pruebas PostgreSQL de exportación y solicitud de eliminación de cuenta."""
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

from api.account_privacy import export_account_data, request_account_deletion  # noqa: E402


def _user() -> str:
    user_id = str(uuid.uuid4())
    email = f"{user_id}@example.invalid"
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id,email,email_normalized,password_hash,display_name,status,created_at,updated_at)
            VALUES (:id,:email,:email,'hash','Privacidad test','active',:now,:now)
        """), {"id": user_id, "email": email, "now": now})
    return user_id


def test_export_contains_user_and_no_secrets():
    user_id = _user()
    data = export_account_data(user_id)
    assert data["user"]["id"] == user_id
    assert "password_hash" not in data["user"]
    assert data["user"]["email_normalized"].endswith("@example.invalid")
    assert "No incluye prompts, respuestas ni secretos" in data["scope"]
    assert data["projects"] == []
    assert data["deletion_requests"] == []


def test_deletion_request_is_idempotent_while_pending():
    user_id = _user()
    first = request_account_deletion(user_id, "Quiero cerrar mi cuenta")
    second = request_account_deletion(user_id, "otra nota")
    assert first["status"] == "pending"
    assert second["status"] == "pending"
    assert second["request_id"] == first["id"] if "id" in first else second["request_id"] == first["request_id"]
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM account_deletion_requests WHERE user_id=:id AND status='pending'"), {"id": user_id}).scalar_one()
    assert count == 1
