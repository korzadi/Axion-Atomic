"""Contratos HTTP del checkout de compra única (sin red, sin PostgreSQL).

Cubre el fallo cerrado (QvaPay desactivado), la validación del producto contra
el catálogo aprobado, la creación de orden+invoice con proveedor simulado, el
detalle de orden propia y la verificación/conciliación delegada. No prueba
LNURL real ni cobros (eso es evidencia E2E/CI), sino el contrato y la ausencia
de filtraciones.
"""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from api.checkout_routes import (
    CheckoutOrderCreate,
    create_checkout_order,
    get_checkout_order,
    verify_checkout_order,
)


def _settings(**overrides):
    settings = SimpleNamespace(
        auth_enabled=True,
        qvapay_enabled=True,
        qvapay_user_token=SimpleNamespace(get_secret_value=lambda: "token-simulado"),
        qvapay_lightning_address="axyronatomic@qvpay.me",
        qvapay_request_timeout_seconds=5.0,
    )
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _fake_client(receiving=True, available=True):
    client = MagicMock()
    client.address_status = AsyncMock(return_value=SimpleNamespace(
        receiving=receiving, available=available, fee_usd_pct="0.5",
        min_usd="0.10", max_usd="500", daily_usd="1000", used_24h_usd="0",
    ))
    client.btc_usd_price = AsyncMock(return_value="100000")
    client.create_invoice = AsyncMock(return_value=SimpleNamespace(
        pr="lnbc" + "1" * 100, sats=int(499 * 100_000_000 / (100 * 100000) ) + 1, comment="axy1234567890ab", callback="https://callback.example",
    ))
    return client


class CheckoutCreateTests(unittest.IsolatedAsyncioTestCase):
    async def test_checkout_fails_closed_when_qvapay_disabled(self):
        with patch("api.checkout_routes.settings", _settings(qvapay_enabled=False)):
            with self.assertRaises(HTTPException) as caught:
                await create_checkout_order(CheckoutOrderCreate(product_code="starter_300"), user={"id": "user-a"})
        self.assertEqual(caught.exception.status_code, 503)

    async def test_checkout_rejects_unapproved_product(self):
        with (
            patch("api.checkout_routes.settings", _settings()),
            patch("api.checkout_routes._limit"),
            patch("api.checkout_routes.expire_overdue_orders"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await create_checkout_order(CheckoutOrderCreate(product_code="gold_pack_99999"), user={"id": "user-a"})
        self.assertEqual(caught.exception.status_code, 404)

    async def test_checkout_creates_order_and_exact_invoice(self):
        client = _fake_client()
        order = SimpleNamespace(
            order_id="11111111-1111-1111-1111-111111111111",
            product_code="starter_300", amount_minor=499, currency="USD",
            credits=300, status="pending",
            expires_at=datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc),
        )
        invoice = SimpleNamespace(
            reference="axy" + "ab" * 12, bolt11="lnbc" + "1" * 100, sats=4990,
            btc_usd_price="100000", fee_usd_pct="0.5",
        )
        with (
            patch("api.checkout_routes.settings", _settings()),
            patch("api.checkout_routes.QvaPayLightningClient", return_value=client),
            patch("api.checkout_routes._limit"),
            patch("api.checkout_routes.expire_overdue_orders"),
            patch("api.checkout_routes.create_payment_order", return_value=order) as create_order,
            patch("api.checkout_routes.create_invoice_record", return_value=invoice) as create_record,
        ):
            response = await create_checkout_order(
                CheckoutOrderCreate(product_code="starter_300"), user={"id": "user-a"},
            )
        self.assertEqual(response["order_id"], order.order_id)
        self.assertEqual(response["product_code"], "starter_300")
        self.assertEqual(response["amount_sats"], 4990)
        self.assertTrue(response["bolt11"].startswith("lnbc"))
        create_order.assert_called_once()
        create_record.assert_called_once()
        self.assertEqual(create_order.call_args.kwargs["amount_minor"], 499)
        self.assertEqual(create_order.call_args.kwargs["credits"], 300)

    async def test_checkout_hides_provider_errors(self):
        client = MagicMock()
        client.address_status = AsyncMock(side_effect=RuntimeError("token filtraded en error interno"))
        with (
            patch("api.checkout_routes.settings", _settings()),
            patch("api.checkout_routes.QvaPayLightningClient", return_value=client),
            patch("api.checkout_routes._limit"),
            patch("api.checkout_routes.expire_overdue_orders"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await create_checkout_order(CheckoutOrderCreate(product_code="starter_300"), user={"id": "user-a"})
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("token", caught.exception.detail.lower())


class CheckoutReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_order_returns_own_order_and_invoice(self):
        row = {
            "id": "11111111-1111-1111-1111-111111111111",
            "product_code": "starter_300", "amount_minor": 499, "currency": "USD",
            "credits": 300, "status": "pending", "payment_method": "qvapay_lightning",
            "expires_at": datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc),
            "paid_at": None, "created_at": datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc),
        }
        invoice = {
            "reference": "axy" + "ab" * 12, "bolt11": "lnbc" + "1" * 40,
            "sats": 4990, "status": "created", "btc_usd_price": "100000",
        }
        with (
            patch("api.checkout_routes._limit"),
            patch("api.checkout_routes.expire_overdue_orders"),
            patch("api.checkout_routes._load_own_order", return_value=(row, invoice)),
        ):
            response = await get_checkout_order("11111111-1111-1111-1111-111111111111", user={"id": "user-a"})
        self.assertEqual(response["invoice"]["reference"], invoice["reference"])
        self.assertEqual(response["invoice"]["sats"], 4990)


class CheckoutVerifyTests(unittest.IsolatedAsyncioTestCase):
    async def test_verify_returns_order_status_without_provider_details(self):
        row = {
            "id": "11111111-1111-1111-1111-111111111111",
            "product_code": "starter_300", "amount_minor": 499, "currency": "USD",
            "credits": 300, "status": "paid", "payment_method": "qvapay_lightning",
            "expires_at": datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc),
            "paid_at": datetime(2026, 11, 8, 17, 30, tzinfo=timezone.utc),
            "created_at": datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc),
        }
        with (
            patch("api.checkout_routes.settings", _settings()),
            patch("api.checkout_routes._limit"),
            patch("api.checkout_routes.expire_overdue_orders"),
            patch("api.checkout_routes.fetch_recent_payments", new=AsyncMock(return_value=[])),
            patch("api.checkout_routes.reconcile_lightning_payments", return_value=[SimpleNamespace(order_id="11111111-1111-1111-1111-111111111111", outcome="confirmed")]),
            patch("api.checkout_routes._load_own_order", return_value=(row, None)),
        ):
            response = await verify_checkout_order("11111111-1111-1111-1111-111111111111", user={"id": "user-a"})
        self.assertTrue(response["paid"])
        self.assertEqual(response["outcome"], "confirmed")

    async def test_verify_fails_closed_when_qvapay_disabled(self):
        with patch("api.checkout_routes.settings", _settings(qvapay_enabled=False)):
            with self.assertRaises(HTTPException) as caught:
                await verify_checkout_order("11111111-1111-1111-1111-111111111111", user={"id": "user-a"})
        self.assertEqual(caught.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
