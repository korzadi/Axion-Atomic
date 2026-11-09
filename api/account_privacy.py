"""Exportación de datos y solicitudes de eliminación de cuenta.

Operaciones acotadas al usuario autenticado. La eliminación efectiva NO se
ejecuta automáticamente: se registra una solicitud auditable para revisión del
operador, preservando registros financieros cuando la normativa lo exija.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.database import engine


def _now() -> datetime:
    return datetime.now(timezone.utc)


def export_account_data(user_id: str) -> dict:
    now = _now()
    with engine.connect() as conn:
        user = conn.execute(text("""
            SELECT id, email, email_normalized, display_name, status,
                   email_verified_at, terms_accepted_at, created_at, updated_at, last_login_at
            FROM users WHERE id=:id
        """), {"id": user_id}).mappings().first()
        if user is None:
            return {"user": None, "generated_at": now.isoformat()}

        projects = conn.execute(text("""
            SELECT p.id, p.name, p.created_at, m.role, m.created_at AS joined_at
            FROM project_memberships m
            JOIN projects p ON p.id = m.project_id
            WHERE m.user_id=:id
            ORDER BY p.created_at DESC
        """), {"id": user_id}).mappings().all()

        usage = conn.execute(text("""
            SELECT project_id,
                   COUNT(*) AS requests,
                   COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                   COALESCE(SUM(completion_tokens), 0) AS completion_tokens
            FROM inference_usage_events
            WHERE user_id=:id
            GROUP BY project_id
            ORDER BY requests DESC
        """), {"id": user_id}).mappings().all()

        credits = conn.execute(text("""
            SELECT balance_available, balance_reserved, balance_consumed, updated_at
            FROM credit_balances WHERE user_id=:id
        """), {"id": user_id}).mappings().first()

        ledger = conn.execute(text("""
            SELECT event_type, available_delta, reserved_delta, consumed_delta,
                   credits_amount, currency, reason, created_at
            FROM credit_ledger_events
            WHERE user_id=:id
            ORDER BY created_at DESC
            LIMIT 200
        """), {"id": user_id}).mappings().all()

        deletion = conn.execute(text("""
            SELECT id, status, requested_at, processed_at
            FROM account_deletion_requests
            WHERE user_id=:id
            ORDER BY requested_at DESC
            LIMIT 5
        """), {"id": user_id}).mappings().all()

    def row_to_dict(row):
        data = dict(row)
        for key, value in list(data.items()):
            if hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return data

    return {
        "generated_at": now.isoformat(),
        "scope": "Datos acotados a la cuenta autenticada. No incluye prompts, respuestas ni secretos.",
        "user": row_to_dict(user),
        "projects": [row_to_dict(r) for r in projects],
        "usage_summary": [row_to_dict(r) for r in usage],
        "credits": row_to_dict(credits) if credits else None,
        "credit_ledger_recent": [row_to_dict(r) for r in ledger],
        "deletion_requests": [row_to_dict(r) for r in deletion],
    }


def request_account_deletion(user_id: str, note: str = "") -> dict:
    now = _now()
    request_id = secrets.token_urlsafe(18)
    cleaned_note = (note or "").strip()[:2000] or None
    with engine.begin() as conn:
        existing = conn.execute(text("""
            SELECT id, status, requested_at
            FROM account_deletion_requests
            WHERE user_id=:id AND status='pending'
            LIMIT 1
        """), {"id": user_id}).mappings().first()
        if existing:
            return {"status": "pending", "request_id": existing["id"], "requested_at": existing["requested_at"].isoformat() if hasattr(existing["requested_at"], "isoformat") else existing["requested_at"], "message": "Ya existe una solicitud pendiente para esta cuenta."}
        try:
            conn.execute(text("""
                INSERT INTO account_deletion_requests (id, user_id, status, requested_at, note)
                VALUES (:id, :user_id, 'pending', :now, :note)
            """), {"id": request_id, "user_id": user_id, "now": now, "note": cleaned_note})
        except IntegrityError:
            existing = conn.execute(text("""
                SELECT id, status, requested_at
                FROM account_deletion_requests
                WHERE user_id=:id AND status='pending'
                LIMIT 1
            """), {"id": user_id}).mappings().first()
            if existing:
                return {"status": "pending", "request_id": existing["id"], "requested_at": existing["requested_at"].isoformat() if hasattr(existing["requested_at"], "isoformat") else existing["requested_at"], "message": "Ya existe una solicitud pendiente para esta cuenta."}
            raise
    return {
        "status": "pending",
        "request_id": request_id,
        "requested_at": now.isoformat(),
        "message": "Solicitud registrada. La eliminación efectiva la revisa el operador; no se ejecuta automáticamente.",
    }
