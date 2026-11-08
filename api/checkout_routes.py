"""Checkout de compra única de créditos vía QvaPay Lightning.

Contrato:
- ``POST /billing/checkout/orders`` crea una orden interna ``pending`` y su
  invoice Lightning EXACTA (LNURL callback con el comentario de correlación).
  No mueve dinero; la invoice solo queda creada. Compra única, sin suscripciones.
- ``GET  /billing/checkout/orders/{order_id}`` devuelve la orden propia y su
  invoice abierta (o la última), para que la SPA la muestre al pagar.
- ``POST /billing/checkout/orders/{order_id}/verify`` reconcilia los cobros
  recientes del titular con las invoices abiertas y confirma el pago cuando
  coinciden referencia, sats exactos, destinatario y ``transaction_uuid``.
  La acreditación pasa por ``confirm_verified_payment`` (idempotente).

Fallo cerrado en todo el flujo: sin ``QVAPAY_ENABLED`` el catálogo se publica
pero el checkout responde 503; sin token, 503; cualquier error del proveedor,
503 sin detalles internos. El cliente nunca ve el token, el ``transaction_uuid``
ni los detalles del proveedor.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from api.auth import COOKIE_NAME, CSRF_COOKIE, current_user, require_csrf
from api.commercial_catalog import plan_for_code
from api.config import settings
from api.database import engine
from api.payment_manager import create_payment_order, expire_overdue_orders
from api.qvapay_lightning import (
    QvaPayLightningClient,
    QvaPayLightningError,
    usd_cents_to_sats,
    validate_address_name,
)
from api.qvapay_settlement import (
    create_invoice_record,
    fetch_recent_payments,
    new_payment_reference,
    reconcile_lightning_payments,
)
from api.rate_limit import consume_rate_limit, rate_limit_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing/checkout", tags=["checkout"])
ORDER_TTL_MINUTES = 30


class CheckoutOrderCreate(BaseModel):
    product_code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")


def _session_user(axion_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="La autenticación web aún no está habilitada")
    return current_user(axion_session)


def _csrf_user(
    user=Depends(_session_user),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    require_csrf(user, csrf_cookie, csrf_header)
    return user


def _limit(user_id: str, namespace: str, limit: int, window: timedelta) -> None:
    decision = consume_rate_limit(
        engine=engine,
        bucket_key=rate_limit_key(namespace, str(user_id)),
        limit=limit,
        window=window,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Demasiadas operaciones. Inténtalo más tarde.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def _qvapay_credentials() -> tuple[str, str]:
    if not settings.qvapay_enabled:
        raise HTTPException(status_code=503, detail="Los pagos están desactivados")
    token = (
        settings.qvapay_user_token.get_secret_value()
        if settings.qvapay_user_token is not None
        else None
    )
    if not token:
        raise HTTPException(status_code=503, detail="Los pagos no están configurados")
    address = (settings.qvapay_lightning_address or "").strip()
    if "@" not in address:
        raise HTTPException(status_code=503, detail="Los pagos no están configurados")
    name = address.split("@", 1)[0].strip()
    try:
        validate_address_name(name)
    except QvaPayLightningError:
        raise HTTPException(status_code=503, detail="Los pagos no están configurados") from None
    return token, name


def _load_own_order(order_id: str, user_id: str):
    try:
        normalized = str(UUID(order_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail="Orden no encontrada") from None
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, product_code, amount_minor, currency, credits, status,
                   payment_method, expires_at, paid_at, created_at
            FROM payment_orders
            WHERE id=CAST(:order_id AS UUID) AND user_id=:user_id
        """), {"order_id": normalized, "user_id": user_id}).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        invoice = conn.execute(text("""
            SELECT reference, bolt11, sats, status, btc_usd_price
            FROM payment_invoices
            WHERE order_id=CAST(:order_id AS UUID)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """), {"order_id": normalized}).mappings().first()
    return row, invoice


def _order_view(row, invoice) -> dict:
    result = {
        "order_id": str(row["id"]),
        "product_code": row["product_code"],
        "amount_minor": int(row["amount_minor"]),
        "currency": row["currency"].strip(),
        "credits": int(row["credits"]),
        "status": row["status"],
        "payment_method": row["payment_method"],
        "expires_at": row["expires_at"],
        "paid_at": row["paid_at"],
        "created_at": row["created_at"],
        "invoice": None,
    }
    if invoice is not None:
        result["invoice"] = {
            "reference": invoice["reference"],
            "bolt11": invoice["bolt11"],
            "sats": int(invoice["sats"]),
            "status": invoice["status"],
            "btc_usd_price": str(invoice["btc_usd_price"]),
        }
    return result


@router.post("/orders", status_code=201)
async def create_checkout_order(req: CheckoutOrderCreate, user=Depends(_csrf_user)):
    token, name = _qvapay_credentials()
    product = plan_for_code(req.product_code)
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no disponible")
    _limit(str(user["id"]), "billing:checkout:user", 10, timedelta(minutes=1))
    await run_in_threadpool(expire_overdue_orders, engine=engine, limit=20)

    client = QvaPayLightningClient(timeout=settings.qvapay_request_timeout_seconds)
    try:
        status = await client.address_status(token)
        if not status.receiving or not status.available:
            raise HTTPException(status_code=503, detail="Los pagos no están disponibles en este momento")
        price = await client.btc_usd_price()
        sats = usd_cents_to_sats(int(product["price_minor"]), price)
        reference = new_payment_reference()
        invoice = await client.create_invoice(name=name, sats=sats, comment=reference)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Checkout: QvaPay no pudo crear la invoice")
        raise HTTPException(
            status_code=503,
            detail="No se pudo crear el cobro en este momento. Inténtalo más tarde.",
        ) from None

    now = datetime.now(timezone.utc)
    order = await run_in_threadpool(
        create_payment_order,
        engine=engine, user_id=str(user["id"]), product_code=product["code"],
        amount_minor=int(product["price_minor"]), credits=int(product["credits"]),
        expires_at=now + timedelta(minutes=ORDER_TTL_MINUTES), now=now,
    )
    try:
        record = await run_in_threadpool(
            create_invoice_record,
            engine=engine, order_id=order.order_id, bolt11=invoice.pr,
            reference=reference, sats=sats,
            btc_usd_price=price, fee_usd_pct=status.fee_usd_pct,
        )
    except Exception:
        logger.exception("Checkout: orden %s creada pero no se pudo persistir la invoice", order.order_id)
        raise HTTPException(
            status_code=503,
            detail="No se pudo registrar el cobro. La orden expirará sin efecto; reinténtalo.",
        ) from None

    return {
        "order_id": order.order_id,
        "product_code": order.product_code,
        "amount_minor": order.amount_minor,
        "currency": order.currency,
        "credits": order.credits,
        "reference": record.reference,
        "bolt11": record.bolt11,
        "amount_sats": record.sats,
        "btc_usd_price": str(record.btc_usd_price),
        "fee_usd_pct": str(record.fee_usd_pct),
        "expires_at": order.expires_at,
        "status": order.status,
    }


@router.get("/orders/{order_id}")
async def get_checkout_order(order_id: str, user=Depends(_session_user)):
    _limit(str(user["id"]), "billing:checkout:read", 60, timedelta(minutes=1))
    await run_in_threadpool(expire_overdue_orders, engine=engine, limit=20)
    row, invoice = _load_own_order(order_id, str(user["id"]))
    return _order_view(row, invoice)


@router.post("/orders/{order_id}/verify")
async def verify_checkout_order(order_id: str, user=Depends(_csrf_user)):
    token, _name = _qvapay_credentials()
    _limit(str(user["id"]), "billing:checkout:verify", 30, timedelta(minutes=1))
    await run_in_threadpool(expire_overdue_orders, engine=engine, limit=20)
    try:
        order_id = str(UUID(order_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail="Orden no encontrada") from None

    client = QvaPayLightningClient(timeout=settings.qvapay_request_timeout_seconds)
    try:
        payments = await fetch_recent_payments(client, token=token, max_pages=2)
    except QvaPayLightningError:
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar el estado del pago. Inténtalo de nuevo.",
        ) from None
    try:
        results = await run_in_threadpool(
            reconcile_lightning_payments,
            engine=engine,
            payments=payments,
            recipient=settings.qvapay_lightning_address,
            actor=str(user["id"]),
        )
    except Exception:
        logger.exception("Checkout: la conciliación no pudo completarse")
        raise HTTPException(
            status_code=503,
            detail="La verificación no pudo completarse. Inténtalo de nuevo.",
        ) from None

    row, _invoice = _load_own_order(order_id, str(user["id"]))
    outcome = next((item for item in results if item.order_id == order_id), None)
    return {
        "order_id": order_id,
        "status": row["status"],
        "paid": row["status"] == "paid",
        "outcome": outcome.outcome if outcome is not None else "no_matching_payment",
    }
