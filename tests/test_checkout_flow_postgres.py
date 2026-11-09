"""Integración PostgreSQL del flujo completo de compra (proveedor simulado).

Demuestra de punta a punta, contra una base de datos real:

1. POST /billing/checkout/orders → orden interna ``pending`` + invoice Lightning
   EXACTA (LNURL simulado: la respuesta del proveedor se inyecta por el cliente
   inyectable del adaptador).
2. El proveedor confirma el pago (referencia + sats exactos + destinatario +
   ``transaction_uuid``).
3. POST /billing/checkout/orders/{order_id}/verify → reconciliación y acreditación
   transaccional idempotente vía ``reconcile_lightning_payments`` real.
4. El usuario recibe exactamente una vez los 300 créditos; la re-verificación
   no duplica el lote ni los asientos.

No es una prueba contra QvaPay real: el borde HTTP del proveedor está simulado.
Sí ejecuta el código real de órdenes, persistencia, conciliación y ledger.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

from api import checkout_routes  # noqa: E402
from api.checkout_routes import CheckoutOrderCreate, create_checkout_order, verify_checkout_order  # noqa: E402
from api.qvapay_lightning import LightningPayment  # noqa: E402


def _active_user():
    user_id = str(uuid.uuid4())
    email = f"{user_id}@example.invalid"
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id, email, email_normalized, password_hash,
                               display_name, status, email_verified_at, terms_accepted_at)
            VALUES (:id, :email, :email, 'test-hash', 'Checkout flow test', 'active', now(), now())
        """), {"id": user_id, "email": email})
    return user_id


def _purchased_lots(user_id):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT source, source_reference, granted_credits, available_credits
            FROM billing_credit_lots WHERE user_id=:u AND source='purchased'
        """), {"u": user_id}).mappings().all()


def _order(order_id):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT status, paid_at FROM payment_orders WHERE id=CAST(:id AS UUID)"
        ), {"id": order_id}).mappings().one()


def _ledger_grants(user_id):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT event_type, available_delta FROM billing_credit_ledger
            WHERE user_id=:u AND event_type='grant'
        """), {"u": user_id}).mappings().all()


class FakeQvaPayClient:
    """Doble del adaptador HTTP: simula SOLO el borde con QvaPay."""

    def __init__(self, **_kwargs):
        pass

    async def address_status(self, token, *, page=1):
        return SimpleNamespace(
            receiving=True, available=True, fee_usd_pct=Decimal("0.5"),
            min_usd=Decimal("0.10"), max_usd=Decimal("500"),
            daily_usd=Decimal("1000"), used_24h_usd=Decimal("0"),
            visible=True, name="axyronatomic",
            lnurl="https://qvpay.me/.well-known/lnurlp/axyronatomic",
            address="axyronatomic", status="ACTIVE", receive_as="BTC", payments=(),
        )

    async def btc_usd_price(self):
        return Decimal("100000")

    async def create_invoice(self, *, name, sats, comment):
        return SimpleNamespace(
            pr="lnbc" + "1" * 100,
            sats=sats,
            comment=comment,
            callback="https://callback.example/invoice",
        )


def test_full_purchase_flow_end_to_end():
    asyncio.run(_flow())


async def _flow():
    user_id = _active_user()
    with (
        patch.object(checkout_routes.settings, "qvapay_enabled", True),
        patch.object(checkout_routes.settings, "qvapay_lightning_address", "axyronatomic@qvpay.me"),
        patch.object(checkout_routes.settings, "qvapay_user_token",
                     SimpleNamespace(get_secret_value=lambda: "token-de-prueba")),
        patch.object(checkout_routes, "QvaPayLightningClient", FakeQvaPayClient),
        patch.object(checkout_routes, "_limit"),
        patch.object(checkout_routes, "expire_overdue_orders", return_value=0),
    ):
        created = await create_checkout_order(
            CheckoutOrderCreate(product_code="starter_300"), user={"id": user_id},
        )

    order_id = created["order_id"]
    assert created["amount_sats"] == 4990  # 499 centavos USD / 100.000 USD/BTC, al alza
    assert created["reference"].startswith("axy")
    assert created["bolt11"].startswith("lnbc")

    payment = LightningPayment(
        uuid=str(uuid.uuid4()),
        transaction_uuid="tx-flow-test-1",
        address="axyronatomic@qvpay.me",
        sats=created["amount_sats"],
        credit_usd=Decimal("4.97"),
        credit_unit="USD",
        comment=created["reference"],
        paid_at=datetime.now(timezone.utc),
    )
    with (
        patch.object(checkout_routes, "_qvapay_credentials", return_value=("token-de-prueba", "axyronatomic")),
        patch.object(checkout_routes, "_limit"),
        patch.object(checkout_routes, "expire_overdue_orders", return_value=0),
        patch.object(checkout_routes, "fetch_recent_payments", new=AsyncMock(return_value=[payment])),
    ):
        first = await verify_checkout_order(order_id, user={"id": user_id})

    assert first["paid"] is True
    assert first["status"] == "paid"
    assert first["outcome"] == "confirmed"

    lots = _purchased_lots(user_id)
    assert len(lots) == 1
    assert lots[0]["granted_credits"] == 300
    assert lots[0]["available_credits"] == 300
    grants = _ledger_grants(user_id)
    assert any(int(row["available_delta"]) == 300 for row in grants)

    order = _order(order_id)
    assert order["status"] == "paid"
    assert order["paid_at"] is not None

    # Re-verificación: idempotente — no duplica lote ni asiento.
    with (
        patch.object(checkout_routes, "_qvapay_credentials", return_value=("token-de-prueba", "axyronatomic")),
        patch.object(checkout_routes, "_limit"),
        patch.object(checkout_routes, "expire_overdue_orders", return_value=0),
        patch.object(checkout_routes, "fetch_recent_payments", new=AsyncMock(return_value=[payment])),
    ):
        second = await verify_checkout_order(order_id, user={"id": user_id})

    assert second["paid"] is True
    lots = _purchased_lots(user_id)
    assert len(lots) == 1
    assert sum(int(row["available_credits"]) for row in lots) == 300
