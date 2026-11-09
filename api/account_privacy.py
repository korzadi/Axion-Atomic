"""Exportación de datos y solicitudes de eliminación de cuenta.

Operaciones acotadas al usuario autenticado. La eliminación efectiva NO se
ejecuta automáticamente: se registra una solicitud auditable para revisión del
operador, preservando registros financieros cuando la normativa lo exija.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from api.database import engine


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(row):
    data = dict(row)
    for key, value in list(data.items()):
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data


def export_account_data(user_id: str) -> dict:
    now = _now()
    result: dict = {
        "generated_at": now.isoformat(),
        "scope": "Datos acotados a la cuenta autenticada. No incluye prompts, respuestas ni secretos.",
        "user": None,
        "projects": [],
        "usage_summary": [],
        "credits": None,
        "credit_ledger_recent": [],
        "deletion_requests": [],
    }
    with engine.connect() as conn:
        user = conn.execute(text("""
            SELECT id, email, email_normalized, display_name, status,
                   email_verified_at, terms_accepted_at, created_at, updated_at, last_login_at
            FROM users WHERE id=:id
        """), {"id": user_id}).mappings().first()
        if user is None:
            return result
        result["user"] = _row(user)

        result["projects"] = [_row(r) for r in conn.execute(text("""
            SELECT p.id, p.name, p.created_at, m.role, m.created_at AS joined_at
            FROM project_memberships m
            JOIN projects p ON p.id = m.project_id
            WHERE m.user_id=:id
            ORDER BY p.created_at DESC
        """), {"id": user_id}).mappings().all()]

        result["deletion_requests"] = [_row(r) for r in conn.execute(text("""
            SELECT id, status, requested_at, processed_at
            FROM account_deletion_requests
            WHERE user_id=:id
            ORDER BY requested_at DESC
            LIMIT 5
        """), {"id": user_id}).mappings().all()]

        # Secciones opcionales: cada una con savepoint para no abortar la lectura
        # si una tabla no existe o su esquema difiere en un entorno de pruebas.
        for section, query in (
            ("usage_summary", """
                SELECT project_id,
                       COUNT(*) AS requests,
                       COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens
                FROM inference_usage_events
                WHERE user_id=:id
                GROUP BY project_id
                ORDER BY requests DESC
            """),
            ("credits", """
                SELECT COUNT(*) AS lot_count,
                       COALESCE(SUM(granted_credits), 0) AS granted_credits,
                       COALESCE(SUM(available_credits), 0) AS available_credits,
                       COALESCE(SUM(reserved_credits), 0) AS reserved_credits,
                       COALESCE(SUM(consumed_credits), 0) AS consumed_credits
                FROM billing_credit_lots
                WHERE user_id=:id
            """),
            ("credit_ledger_recent", """
                SELECT event_type, available_delta, reserved_delta, consumed_delta,
                       reason, created_at
                FROM billing_credit_ledger
                WHERE user_id=:id
                ORDER BY created_at DESC, id DESC
                LIMIT 50
            """),
        ):
            try:
                with conn.begin_nested():
                    rows = conn.execute(text(query), {"id": user_id}).mappings().all()
                if section == "credits":
                    result[section] = _row(rows[0]) if rows else None
                else:
                    result[section] = [_row(r) for r in rows]
            except SQLAlchemyError:
                try:
                    conn.rollback()
                except Exception:
                    pass
                result[section] = None if section == "credits" else []
    return result


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
            return {
                "status": "pending",
                "request_id": existing["id"],
                "requested_at": existing["requested_at"].isoformat() if hasattr(existing["requested_at"], "isoformat") else existing["requested_at"],
                "message": "Ya existe una solicitud pendiente para esta cuenta.",
            }
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
                return {
                    "status": "pending",
                    "request_id": existing["id"],
                    "requested_at": existing["requested_at"].isoformat() if hasattr(existing["requested_at"], "isoformat") else existing["requested_at"],
                    "message": "Ya existe una solicitud pendiente para esta cuenta.",
                }
            raise
    return {
        "status": "pending",
        "request_id": request_id,
        "requested_at": now.isoformat(),
        "message": "Solicitud registrada. La eliminación efectiva la revisa el operador; no se ejecuta automáticamente.",
    }
