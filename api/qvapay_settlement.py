"""Persistencia y conciliación de invoices Lightning de QvaPay.

Este módulo no crea órdenes, no expone HTTP y no acredita créditos por sí solo.
Reutiliza la verificación server-to-server de ``api.payment_manager`` tras
confirmar que el cobro coincide exactamente con la invoice abierta: mismo
destinatario, mismo comentario de correlación y mismos sats.

No existe webhook firmado para Lightning Address: la conciliación consulta la
API del titular con su token y pagina los últimos cobros. El comentario no es
prueba aislada de pago; solo correlaciona junto con sats exactos, dirección
destino e identificador de transacción.
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.engine import Engine

from api.payment_manager import (
    PaymentOrderNotFound,
    PaymentOrderStateError,
    VerifiedPayment,
    confirm_verified_payment,
    get_payment_order,
    record_payment_observation,
)
from api.qvapay_lightning import (
    LightningPayment,
    QvaPayLightningClient,
    QvaPayLightningConfigError,
    match_payment,
)

PROVIDER = "qvapay_lightning"
PAGE_SIZE = 20
MAX_PAGES = 5


class InvoicePersistenceError(ValueError):
    pass


class InvoiceOrderStateError(InvoicePersistenceError):
    pass


@dataclass(frozen=True)
class LightningInvoiceRecord:
    invoice_id: str
    order_id: str
    reference: str
    bolt11: str
    sats: int
    amount_minor: int
    btc_usd_price: Decimal
    fee_usd_pct: Decimal
    status: str
    provider_transaction_id: str | None


@dataclass(frozen=True)
class ReconciliationResult:
    order_id: str
    reference: str
    outcome: str
    provider_transaction_id: str | None
    sats: int | None


def new_payment_reference() -> str:
    """Referencia unguessable y segura para el comentario LNURL (LUD-12)."""
    return "axy" + secrets.token_hex(12)


def _decimal_positive(value, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvoicePersistenceError(f"{field} inválido") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise InvoicePersistenceError(f"{field} debe ser positivo")
    return parsed


def _non_negative_decimal(value, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvoicePersistenceError(f"{field} inválido") from exc
    if not parsed.is_finite() or parsed < 0:
        raise InvoicePersistenceError(f"{field} inválido")
    return parsed


def create_invoice_record(
    *,
    engine: Engine,
    order_id: str,
    bolt11: str,
    reference: str,
    sats: int,
    btc_usd_price,
    fee_usd_pct,
    now: datetime | None = None,
) -> LightningInvoiceRecord:
    """Persiste la invoice de una orden pendiente y supersede la anterior abierta."""
    if not isinstance(reference, str) or not 8 <= len(reference) <= 64:
        raise InvoicePersistenceError("Referencia inválida")
    if not isinstance(bolt11, str) or not bolt11.startswith("lnbc") or len(bolt11) > 4096:
        raise InvoicePersistenceError("Invoice Lightning inválida")
    if isinstance(sats, bool) or not isinstance(sats, int) or sats <= 0:
        raise InvoicePersistenceError("Los sats deben ser un entero positivo")
    price = _decimal_positive(btc_usd_price, "btc_usd_price")
    fee = _non_negative_decimal(fee_usd_pct, "fee_usd_pct")
    if fee >= 100:
        raise InvoicePersistenceError("fee_usd_pct fuera de rango")
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        order_uuid = str(uuid.UUID(str(order_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PaymentOrderNotFound("Orden inexistente") from exc

    invoice_id = str(uuid.uuid4())
    with engine.begin() as conn:
        order = conn.execute(text("""
            SELECT id, user_id, amount_minor, currency, status
            FROM payment_orders WHERE id=CAST(:id AS UUID) FOR UPDATE
        """), {"id": order_uuid}).mappings().first()
        if order is None:
            raise PaymentOrderNotFound("Orden inexistente")
        if order["status"] != "pending":
            raise InvoiceOrderStateError("La orden no acepta invoices en su estado actual")
        amount_minor = order["amount_minor"]
        conn.execute(text("""
            UPDATE payment_invoices
               SET status='superseded', updated_at=:now
             WHERE order_id=CAST(:id AS UUID) AND status='created'
        """), {"id": order_uuid, "now": instant})
        conn.execute(text("""
            INSERT INTO payment_invoices
                (id, order_id, provider, reference, bolt11, comment, sats,
                 amount_minor, currency, btc_usd_price, fee_usd_pct, status,
                 created_at, updated_at)
            VALUES (CAST(:id AS UUID), CAST(:order_id AS UUID), :provider,
                    :reference, :bolt11, :reference, :sats, :amount_minor, 'USD',
                    :price, :fee, 'created', :now, :now)
        """), {
            "id": invoice_id, "order_id": order_uuid, "provider": PROVIDER,
            "reference": reference, "bolt11": bolt11, "sats": sats,
            "amount_minor": amount_minor, "price": price, "fee": fee, "now": instant,
        })
    return LightningInvoiceRecord(
        invoice_id=invoice_id, order_id=order_uuid, reference=reference,
        bolt11=bolt11, sats=sats, amount_minor=amount_minor,
        btc_usd_price=price, fee_usd_pct=fee, status="created",
        provider_transaction_id=None,
    )


def _open_invoices(engine: Engine):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT i.id, i.order_id, i.reference, i.sats, i.amount_minor,
                   o.status AS order_status, o.expires_at
            FROM payment_invoices i
            JOIN payment_orders o ON o.id = i.order_id
            WHERE i.status = 'created'
            ORDER BY i.created_at
        """)).mappings().all()


def reconcile_lightning_payments(
    *,
    engine: Engine,
    payments: list[LightningPayment] | tuple[LightningPayment, ...],
    recipient: str,
    actor: str = "qvapay-lightning-sync",
    now: datetime | None = None,
) -> list[ReconciliationResult]:
    """Concilia cobros observados con invoices abiertas; nunca confía en comentarios.

    Solo confirma cuando coinciden comentario (referencia), sats exactos,
    destinatario e identificador de transacción. La confirmación delega en
    ``confirm_verified_payment``, que aplica las reglas de importe, expiración
    e idempotencia y acredita una única vez.
    """
    recipient = (recipient or "").strip()
    if not recipient:
        raise InvoicePersistenceError("Falta el destinatario Lightning")
    instant = now or datetime.now(timezone.utc)
    results: list[ReconciliationResult] = []
    for row in _open_invoices(engine):
        order_id = str(row["order_id"])
        reference = row["reference"]
        if row["order_status"] != "pending":
            results.append(ReconciliationResult(order_id, reference, "order_not_pending", None, None))
            continue
        payment = match_payment(payments, reference=reference, sats=row["sats"], address=recipient)
        if payment is None:
            results.append(ReconciliationResult(order_id, reference, "unmatched", None, None))
            continue
        record_payment_observation(
            engine=engine,
            order_id=order_id,
            event_key=f"lightning-observed:{payment.transaction_uuid}:{order_id}",
            actor=actor,
            details={
                "provider": PROVIDER,
                "sats": payment.sats,
                "credit_usd": str(payment.credit_usd),
                "transaction_uuid": payment.transaction_uuid,
                "reference": reference,
                "source": "provider_api",
            },
        )
        verified = VerifiedPayment(
            provider_transaction_id=payment.transaction_uuid,
            amount_minor=row["amount_minor"],
            currency="USD",
            recipient=recipient,
            verification_source="provider_api",
            verified_at=payment.paid_at,
        )
        try:
            confirmed = confirm_verified_payment(
                engine=engine, order_id=order_id, payment=verified,
                expected_recipient=recipient,
            )
        except PaymentOrderStateError:
            results.append(ReconciliationResult(order_id, reference, "state_conflict", payment.transaction_uuid, payment.sats))
            continue
        with engine.begin() as conn:
            order = conn.execute(text(
                "SELECT status FROM payment_orders WHERE id=CAST(:id AS UUID)"
            ), {"id": order_id}).scalar_one()
            if order == "paid":
                conn.execute(text("""
                    UPDATE payment_invoices
                       SET status='paid', provider_transaction_id=:tx,
                           paid_at=:paid_at, updated_at=:now
                     WHERE id=CAST(:id AS UUID) AND status='created'
                """), {
                    "tx": payment.transaction_uuid, "paid_at": payment.paid_at,
                    "now": instant, "id": str(row["id"]),
                })
                outcome = "confirmed" if confirmed else "already_confirmed"
            else:
                outcome = "under_review"
        results.append(ReconciliationResult(order_id, reference, outcome, payment.transaction_uuid, payment.sats))
    return results


def list_open_invoices(engine: Engine) -> list[LightningInvoiceRecord]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, order_id, reference, bolt11, sats, amount_minor,
                   btc_usd_price, fee_usd_pct, status, provider_transaction_id
            FROM payment_invoices WHERE status = 'created'
            ORDER BY created_at
        """)).mappings().all()
    return [
        LightningInvoiceRecord(
            invoice_id=str(r["id"]), order_id=str(r["order_id"]),
            reference=r["reference"], bolt11=r["bolt11"], sats=r["sats"],
            amount_minor=r["amount_minor"], btc_usd_price=r["btc_usd_price"],
            fee_usd_pct=r["fee_usd_pct"], status=r["status"],
            provider_transaction_id=r["provider_transaction_id"],
        )
        for r in rows
    ]


async def fetch_recent_payments(
    client: QvaPayLightningClient,
    *,
    token: str,
    max_pages: int = MAX_PAGES,
) -> list[LightningPayment]:
    """Pagina los últimos cobros del titular (20 por página, máximo ``max_pages``)."""
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise QvaPayLightningConfigError("max_pages debe ser un entero positivo")
    seen: set[str] = set()
    payments: list[LightningPayment] = []
    for page in range(1, max_pages + 1):
        status = await client.address_status(token, page=page)
        batch = list(status.payments)
        new_items = [p for p in batch if p.transaction_uuid not in seen]
        payments.extend(new_items)
        if len(batch) < PAGE_SIZE or not new_items:
            break
        seen.update(p.transaction_uuid for p in batch)
    return payments
