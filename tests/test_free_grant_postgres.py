"""Integración PostgreSQL de la concesión FREE de créditos.

Fija el contrato de la verificación de correo + llmado a concesión:
- activación verifica la cuenta Y concede 50 créditos en la misma transacción;
- la concesión es única por usuario (UNIQUE(source, source_reference));
- si la concesión falla, la activación completa se revierte (rollback total);
- OAuth también concede FREE la primera vez, de forma idempotente.
"""
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

from api.auth_recovery_routes import _activate_and_grant  # noqa: E402
from api.billing_reservations import grant_verification_credits  # noqa: E402
from api.email_verification import (  # noqa: E402
    consume_email_verification_token,
    issue_email_verification_token,
)


def _pending_user():
    user_id = str(uuid.uuid4())
    email = f"{user_id}@example.invalid"
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id,email,email_normalized,password_hash,display_name,status)
            VALUES (:id,:email,:email,'test-hash','Free grant test','pending_verification')
        """), {"id": user_id, "email": email})
    return user_id


def _lot(user_id):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT source, source_reference, granted_credits, available_credits
            FROM billing_credit_lots WHERE user_id=:user_id
        """), {"user_id": user_id}).mappings().all()


def _ledger(user_id):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT event_type, available_delta FROM billing_credit_ledger WHERE user_id=:user_id
        """), {"user_id": user_id}).mappings().all()


def test_verify_email_activates_account_and_grants_50_credits():
    user_id = _pending_user()
    issued = issue_email_verification_token(engine=engine, user_id=user_id)
    activated = consume_email_verification_token(
        engine=engine, token=issued.token, on_activate=_activate_and_grant,
    )
    assert activated == user_id
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status,email_verified_at FROM users WHERE id=:id"), {"id": user_id}).one()
    assert row.status == "active"
    assert row.email_verified_at is not None
    lots = _lot(user_id)
    assert len(lots) == 1
    assert lots[0]["source"] == "promotion"
    assert lots[0]["source_reference"] == f"free-verify:{user_id}"
    assert lots[0]["granted_credits"] == 50
    assert lots[0]["available_credits"] == 50
    assert _ledger(user_id)[0]["event_type"] == "grant"
    assert _ledger(user_id)[0]["available_delta"] == 50


def test_free_grant_is_idempotent_on_retry():
    user_id = _pending_user()
    assert grant_verification_credits(engine=engine, user_id=user_id) is True
    assert grant_verification_credits(engine=engine, user_id=user_id) is False
    lots = _lot(user_id)
    assert len(lots) == 1
    assert lots[0]["available_credits"] == 50


def test_failed_grant_rolls_back_the_activation():
    user_id = _pending_user()
    issued = issue_email_verification_token(engine=engine, user_id=user_id)

    def boom(conn, activated_user_id):
        raise RuntimeError("fallo inyectado en la concesión")

    with pytest.raises(RuntimeError):
        consume_email_verification_token(engine=engine, token=issued.token, on_activate=boom)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT status FROM users WHERE id=:id"), {"id": user_id}).one()
        token_row = conn.execute(text(
            "SELECT consumed_at FROM email_verification_tokens WHERE user_id=:user_id"
        ), {"user_id": user_id}).one()
    assert row.status == "pending_verification"
    assert token_row.consumed_at is None
    assert _lot(user_id) == []
