"""Gestión interna de órdenes; no es un adaptador QvaPay ni un endpoint HTTP.

La confirmación solo debe invocarse desde un adaptador que haya verificado
la transacción con evidencia servidor-a-servidor auténtica. Este módulo no
acepta capturas, referencias declaradas por el navegador ni callbacks sin validar.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine


class PaymentOrderError(ValueError):
    pass


class PaymentOrderNotFound(LookupError):
    pass


class PaymentOrderStateError(PaymentOrderError):
    pass


@dataclass(frozen=True)
class PaymentOrder:
    order_id: str
    user_id: str
    product_code: str
    amount_minor: int
    currency: str
    credits: int
    status: str
    expires_at: datetime


@dataclass(frozen=True)
class VerifiedPayment:
    """Datos normalizados por el futuro adaptador tras verificar con QvaPay."""
    provider_transaction_id: str
    amount_minor: int
    currency: str
    recipient: str
    verification_source: str
    verified_at: datetime


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PaymentOrderError(f"{field} debe incluir zona horaria")
    return value.astimezone(timezone.utc)


def create_payment_order(
    *, engine: Engine, user_id: str, product_code: str,
    amount_minor: int, credits: int, expires_at: datetime,
    now: datetime | None = None,
) -> PaymentOrder:
    if not user_id or not product_code or len(product_code) > 80:
        raise PaymentOrderError("Usuario y producto son obligatorios")
    for value, name in ((amount_minor, "amount_minor"), (credits, "credits")):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PaymentOrderError(f"{name} debe ser un entero positivo")
    instant = _utc(now or datetime.now(timezone.utc), "now")
    expiry = _utc(expires_at, "expires_at")
    if expiry <= instant:
        raise PaymentOrderError("La orden debe vencer en el futuro")
    order_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO payment_orders
                (id, user_id, product_code, amount_minor, currency, credits,
                 status, payment_method, expires_at, created_at, updated_at)
            VALUES (CAST(:id AS UUID), :user_id, :product_code, :amount_minor,
                    'USD', :credits, 'pending', 'qvapay_lightning',
                    :expires_at, :now, :now)
        """), {
            "id": order_id, "user_id": user_id, "product_code": product_code,
            "amount_minor": amount_minor, "credits": credits,
            "expires_at": expiry, "now": instant,
        })
        conn.execute(text("""
            INSERT INTO payment_order_events (id, order_id, event_type, event_key, details, actor)
            VALUES (CAST(:id AS UUID), CAST(:order_id AS UUID), 'created',
                    :event_key, CAST(:details AS JSONB), 'system')
        """), {
            "id": str(uuid.uuid4()), "order_id": order_id,
            "event_key": f"order-created:{order_id}",
            "details": '{"method":"qvapay_lightning","currency":"USD"}',
        })
    return PaymentOrder(
        order_id, user_id, product_code, amount_minor, "USD", credits, "pending", expiry
    )


def get_payment_order(*, engine: Engine, user_id: str, order_id: str) -> PaymentOrder:
    try:
        order_uuid = str(uuid.UUID(order_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PaymentOrderNotFound("Orden inexistente") from exc
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, user_id, product_code, amount_minor, currency, credits,
                   status, expires_at
            FROM payment_orders WHERE id=CAST(:id AS UUID) AND user_id=:user_id
        """), {"id": order_uuid, "user_id": user_id}).mappings().first()
    if row is None:
        raise PaymentOrderNotFound("Orden inexistente")
    return PaymentOrder(
        str(row["id"]), row["user_id"], row["product_code"], row["amount_minor"],
        row["currency"].strip(), row["credits"], row["status"], row["expires_at"],
    )


def record_payment_observation(
    *, engine: Engine, order_id: str, event_key: str, actor: str,
    details: dict,
) -> bool:
    """Registra una observación no confiable; jamás marca pagado ni acredita."""
    if not event_key or len(event_key) > 200 or not actor or len(actor) > 120:
        raise PaymentOrderError("Clave de evento y actor son obligatorios")
    import json
    order_uuid = str(uuid.UUID(order_id))
    with engine.begin() as conn:
        exists = conn.execute(text("""
            SELECT 1 FROM payment_orders WHERE id=CAST(:id AS UUID) FOR UPDATE
        """), {"id": order_uuid}).first()
        if not exists:
            raise PaymentOrderNotFound("Orden inexistente")
        result = conn.execute(text("""
            INSERT INTO payment_order_events (id, order_id, event_type, event_key, details, actor)
            VALUES (CAST(:id AS UUID), CAST(:order_id AS UUID), 'payment_observed',
                    :event_key, CAST(:details AS JSONB), :actor)
            ON CONFLICT (event_key) DO NOTHING
        """), {
            "id": str(uuid.uuid4()), "order_id": order_uuid, "event_key": event_key,
            "details": json.dumps(details, separators=(",", ":"), sort_keys=True),
            "actor": actor,
        })
        return result.rowcount == 1


def confirm_verified_payment(
    *, engine: Engine, order_id: str, payment: VerifiedPayment,
    expected_recipient: str,
) -> bool:
    """Confirma importe exacto y acredita una sola vez tras verificación externa real.

    No exponer en HTTP hasta implementar y probar el contrato oficial Lightning.
    """
    if not payment.provider_transaction_id or len(payment.provider_transaction_id) > 200:
        raise PaymentOrderError("Identificador de transacción inválido")
    if isinstance(payment.amount_minor, bool) or not isinstance(payment.amount_minor, int) or payment.amount_minor <= 0:
        raise PaymentOrderError("Importe verificado inválido")
    if payment.currency != "USD" or payment.recipient != expected_recipient:
        raise PaymentOrderError("Moneda o destinatario no coinciden")
    if payment.verification_source not in {"provider_api", "signed_webhook", "manual_review"}:
        raise PaymentOrderError("Fuente de verificación no admitida")
    verified_at = _utc(payment.verified_at, "verified_at")
    order_uuid = str(uuid.UUID(order_id))
    with engine.begin() as conn:
        order = conn.execute(text("""
            SELECT id, user_id, amount_minor, currency, credits, status, expires_at
            FROM payment_orders WHERE id=CAST(:id AS UUID) FOR UPDATE
        """), {"id": order_uuid}).mappings().first()
        if order is None:
            raise PaymentOrderNotFound("Orden inexistente")
        if order["status"] == "paid":
            existing = conn.execute(text("""
                SELECT provider_transaction_id FROM payment_transactions
                WHERE order_id=CAST(:id AS UUID)
            """), {"id": order_uuid}).scalar_one_or_none()
            if existing == payment.provider_transaction_id:
                return False
            raise PaymentOrderStateError("La orden ya fue pagada por otra transacción")
        if order["status"] != "pending":
            raise PaymentOrderStateError("La orden no acepta pagos en su estado actual")
        if verified_at > order["expires_at"]:
            conn.execute(text("""
                UPDATE payment_orders SET status='under_review', updated_at=:now
                WHERE id=CAST(:id AS UUID)
            """), {"id": order_uuid, "now": verified_at})
            conn.execute(text("""
                INSERT INTO payment_order_events
                    (id, order_id, event_type, event_key, details, actor, created_at)
                VALUES (CAST(:event_id AS UUID), CAST(:id AS UUID), 'review_required',
                        :event_key, CAST(:details AS JSONB), 'payment-verifier', :now)
            """), {
                "event_id": str(uuid.uuid4()), "id": order_uuid,
                "event_key": f"late-payment-review:{payment.provider_transaction_id}",
                "details": '{"reason":"payment_verified_after_order_expiry"}', "now": verified_at,
            })
            return False
        if payment.amount_minor != order["amount_minor"] or payment.currency != order["currency"].strip():
            conn.execute(text("""
                UPDATE payment_orders SET status='under_review', updated_at=:now
                WHERE id=CAST(:id AS UUID)
            """), {"id": order_uuid, "now": verified_at})
            conn.execute(text("""
                INSERT INTO payment_order_events
                    (id, order_id, event_type, event_key, details, actor, created_at)
                VALUES (CAST(:event_id AS UUID), CAST(:id AS UUID), 'review_required',
                        :event_key, CAST(:details AS JSONB), 'payment-verifier', :now)
            """), {
                "event_id": str(uuid.uuid4()), "id": order_uuid,
                "event_key": f"payment-review:{payment.provider_transaction_id}",
                "details": '{"reason":"amount_or_currency_mismatch"}', "now": verified_at,
            })
            return False

        conn.execute(text("""
            INSERT INTO payment_transactions
                (id, order_id, provider, provider_transaction_id, amount_minor,
                 currency, recipient, verification_source, verified_at)
            VALUES (CAST(:id AS UUID), CAST(:order_id AS UUID), 'qvapay_lightning',
                    :transaction_id, :amount, 'USD', :recipient, :source, :verified_at)
        """), {
            "id": str(uuid.uuid4()), "order_id": order_uuid,
            "transaction_id": payment.provider_transaction_id,
            "amount": payment.amount_minor, "recipient": payment.recipient,
            "source": payment.verification_source, "verified_at": verified_at,
        })
        # Lote comprado y asiento de ledger se crean en la misma transacción que el pago.
        lot_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO billing_credit_lots
                (id, user_id, source, source_reference, granted_credits, available_credits)
            VALUES (CAST(:id AS UUID), :user_id, 'purchased', :reference, :credits, :credits)
        """), {
            "id": lot_id, "user_id": order["user_id"],
            "reference": f"payment-order:{order_uuid}", "credits": order["credits"],
        })
        conn.execute(text("""
            INSERT INTO billing_credit_ledger
                (id, user_id, credit_lot_id, event_type, available_delta,
                 reserved_delta, consumed_delta, idempotency_key, reason)
            VALUES (CAST(:id AS UUID), :user_id, CAST(:lot_id AS UUID), 'grant',
                    :credits, 0, 0, :ledger_key, :reason)
        """), {
            "id": str(uuid.uuid4()), "user_id": order["user_id"], "lot_id": lot_id,
            "credits": order["credits"], "ledger_key": f"payment-grant:{order_uuid}",
            "reason": f"Compra verificada de créditos para orden {order_uuid}",
        })
        conn.execute(text("""
            UPDATE payment_orders SET status='paid', paid_at=:now, updated_at=:now
            WHERE id=CAST(:id AS UUID)
        """), {"id": order_uuid, "now": verified_at})
        conn.execute(text("""
            INSERT INTO payment_order_events
                (id, order_id, event_type, event_key, details, actor, created_at)
            VALUES (CAST(:id AS UUID), CAST(:order_id AS UUID), 'payment_verified',
                    :event_key, CAST(:details AS JSONB), 'payment-verifier', :now)
        """), {
            "id": str(uuid.uuid4()), "order_id": order_uuid,
            "event_key": f"payment-verified:{payment.provider_transaction_id}",
            "details": '{"provider":"qvapay_lightning","credits_granted":true}',
            "now": verified_at,
        })
    return True
