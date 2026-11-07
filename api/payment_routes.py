"""Consultas privadas del historial de pagos del usuario autenticado.

No crea órdenes, no verifica pagos y no expone operaciones administrativas.
"""
from __future__ import annotations

from datetime import timedelta

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from sqlalchemy import text

from api.auth import COOKIE_NAME, current_user
from api.config import settings
from api.database import engine
from api.rate_limit import consume_rate_limit, rate_limit_key

router = APIRouter(prefix="/billing", tags=["billing"])


def _billing_user(axion_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="La autenticación web aún no está habilitada")
    return current_user(axion_session)


def _limit_reads(user: dict) -> None:
    decision = consume_rate_limit(
        engine=engine,
        bucket_key=rate_limit_key("billing:read:user", str(user["id"])),
        limit=120,
        window=timedelta(minutes=1),
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Demasiadas consultas. Inténtalo más tarde.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def _order_view(row) -> dict:
    return {
        "id": str(row["id"]),
        "product_code": row["product_code"],
        "amount_minor": row["amount_minor"],
        "currency": row["currency"].strip(),
        "credits": row["credits"],
        "status": row["status"],
        "payment_method": row["payment_method"],
        "expires_at": row["expires_at"],
        "paid_at": row["paid_at"],
        "created_at": row["created_at"],
    }


@router.get("/credits")
async def get_my_credit_balance(user=Depends(_billing_user)):
    """Consulta saldos reales de cuotas/lotes y últimos movimientos del ledger."""
    _limit_reads(user)
    with engine.connect() as conn:
        quota_rows = conn.execute(text("""
            SELECT quota_kind,
                   COALESCE(SUM(limit_credits), 0) AS granted_credits,
                   COALESCE(SUM(reserved_credits), 0) AS reserved_credits,
                   COALESCE(SUM(consumed_credits), 0) AS consumed_credits,
                   COALESCE(SUM(GREATEST(limit_credits - reserved_credits - consumed_credits, 0)), 0)
                       AS available_credits
            FROM billing_quota_periods
            WHERE user_id=:user_id AND period_start <= now() AND period_end > now()
            GROUP BY quota_kind
            ORDER BY quota_kind
        """), {"user_id": user["id"]}).mappings().all()
        lots = conn.execute(text("""
            SELECT COUNT(*) AS lot_count,
                   COALESCE(SUM(granted_credits), 0) AS granted_credits,
                   COALESCE(SUM(available_credits) FILTER (
                       WHERE expires_at IS NULL OR expires_at > now()
                   ), 0) AS available_credits,
                   COALESCE(SUM(reserved_credits), 0) AS reserved_credits,
                   COALESCE(SUM(consumed_credits), 0) AS consumed_credits
            FROM billing_credit_lots
            WHERE user_id=:user_id
        """), {"user_id": user["id"]}).mappings().one()
        ledger = conn.execute(text("""
            SELECT event_type, available_delta, reserved_delta, consumed_delta,
                   reason, created_at
            FROM billing_credit_ledger
            WHERE user_id=:user_id
            ORDER BY created_at DESC, id DESC
            LIMIT 50
        """), {"user_id": user["id"]}).mappings().all()

    quota_available = sum(int(row["available_credits"]) for row in quota_rows)
    quota_reserved = sum(int(row["reserved_credits"]) for row in quota_rows)
    quota_consumed = sum(int(row["consumed_credits"]) for row in quota_rows)
    purchased_available = int(lots["available_credits"])
    purchased_reserved = int(lots["reserved_credits"])
    purchased_consumed = int(lots["consumed_credits"])
    return {
        "provisioned": bool(quota_rows) or int(lots["lot_count"]) > 0,
        "currency": "credits",
        "totals": {
            "available": quota_available + purchased_available,
            "reserved": quota_reserved + purchased_reserved,
            "consumed": quota_consumed + purchased_consumed,
        },
        "quotas": [dict(row) for row in quota_rows],
        "purchased_lots": {
            "count": int(lots["lot_count"]),
            "granted": int(lots["granted_credits"]),
            "available": purchased_available,
            "reserved": purchased_reserved,
            "consumed": purchased_consumed,
        },
        "recent_ledger": [dict(row) for row in ledger],
    }


@router.get("/orders")
async def list_my_payment_orders(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    user=Depends(_billing_user),
):
    """Lista solo órdenes propias; paginación acotada y sin datos del proveedor."""
    _limit_reads(user)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, product_code, amount_minor, currency, credits, status,
                   payment_method, expires_at, paid_at, created_at
            FROM payment_orders
            WHERE user_id=:user_id
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
        """), {"user_id": user["id"], "limit": limit, "offset": offset}).mappings().all()
        total = conn.execute(text("""
            SELECT count(*) FROM payment_orders WHERE user_id=:user_id
        """), {"user_id": user["id"]}).scalar_one()
    return {"items": [_order_view(row) for row in rows], "limit": limit, "offset": offset, "total": total}


@router.get("/orders/{order_id}")
async def get_my_payment_order(order_id: str, user=Depends(_billing_user)):
    """Devuelve una orden propia; una orden ajena equivale a inexistente."""
    _limit_reads(user)
    try:
        normalized_id = str(UUID(order_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail="Orden no encontrada") from None
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, product_code, amount_minor, currency, credits, status,
                   payment_method, expires_at, paid_at, created_at
            FROM payment_orders
            WHERE id=CAST(:order_id AS UUID) AND user_id=:user_id
        """), {"order_id": normalized_id, "user_id": user["id"]}).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        events = conn.execute(text("""
            SELECT event_type, created_at
            FROM payment_order_events
            WHERE order_id=CAST(:order_id AS UUID)
            ORDER BY created_at ASC, id ASC
        """), {"order_id": normalized_id}).mappings().all()
    result = _order_view(row)
    result["events"] = [{"type": event["event_type"], "created_at": event["created_at"]} for event in events]
    return result
