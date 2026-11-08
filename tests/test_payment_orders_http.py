"""Contratos de las consultas privadas de órdenes de pago.

Estas pruebas cubren la frontera HTTP/servicio sin PostgreSQL: verifican que el
usuario autenticado se propaga a la consulta, que una orden ajena o inválida es
indistinguible de una inexistente y que no se filtran datos del proveedor.
"""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from api.payment_routes import get_my_payment_order, list_my_payment_orders


def _result(rows=None, first=None, scalar=None):
    mappings = MagicMock()
    mappings.all.return_value = rows or []
    mappings.first.return_value = first
    value = MagicMock()
    value.mappings.return_value = mappings
    value.scalar_one.return_value = scalar
    return value


def _order_row(**overrides):
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "product_code": "credits-1000",
        "amount_minor": 500,
        "currency": "USD ",
        "credits": 1000,
        "status": "pending",
        "payment_method": "qvapay_lightning",
        "expires_at": "2026-11-08T12:00:00+00:00",
        "paid_at": None,
        "created_at": "2026-11-08T11:00:00+00:00",
    }
    row.update(overrides)
    return row


class PaymentOrdersHttpTests(unittest.IsolatedAsyncioTestCase):
    def _connection(self, side_effect):
        connection = MagicMock()
        connection.execute.side_effect = side_effect
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        return connection, engine

    async def test_list_orders_scopes_to_authenticated_user_and_hides_provider_data(self):
        connection, engine = self._connection([
            _result(rows=[_order_row()]),
            _result(scalar=1),
        ])
        with (
            patch("api.payment_routes.engine", engine),
            patch("api.payment_routes._limit_reads"),
        ):
            response = await list_my_payment_orders(limit=20, offset=0, user={"id": "user-a"})

        first_params = connection.execute.call_args_list[0].args[1]
        self.assertEqual(first_params["user_id"], "user-a")
        self.assertEqual(response["total"], 1)
        order = response["items"][0]
        self.assertEqual(order["currency"], "USD")
        for forbidden in ("provider_transaction_id", "user_id", "details", "payment_reference"):
            self.assertNotIn(forbidden, order)

    async def test_get_order_returns_own_order_and_only_safe_events(self):
        connection, engine = self._connection([
            _result(first=_order_row()),
            _result(rows=[{
                "event_type": "created",
                "created_at": "2026-11-08T11:00:00+00:00",
                "details": {"internal": "must-not-leak"},
                "actor": "system",
            }]),
        ])
        with (
            patch("api.payment_routes.engine", engine),
            patch("api.payment_routes._limit_reads"),
        ):
            response = await get_my_payment_order(
                "11111111-1111-1111-1111-111111111111", user={"id": "user-a"}
            )

        params = connection.execute.call_args_list[0].args[1]
        self.assertEqual(params["user_id"], "user-a")
        self.assertEqual(response["events"], [{
            "type": "created",
            "created_at": "2026-11-08T11:00:00+00:00",
        }])
        self.assertNotIn("details", response["events"][0])
        self.assertNotIn("actor", response["events"][0])

    async def test_foreign_or_missing_order_is_not_found(self):
        _connection, engine = self._connection([_result(first=None)])
        with (
            patch("api.payment_routes.engine", engine),
            patch("api.payment_routes._limit_reads"),
        ):
            with self.assertRaises(HTTPException) as denied:
                await get_my_payment_order(
                    "11111111-1111-1111-1111-111111111111", user={"id": "other-user"}
                )
        self.assertEqual(denied.exception.status_code, 404)
        self.assertEqual(denied.exception.detail, "Orden no encontrada")

    async def test_malformed_order_id_is_rejected_before_database_access(self):
        _connection, engine = self._connection([])
        with (
            patch("api.payment_routes.engine", engine),
            patch("api.payment_routes._limit_reads"),
        ):
            with self.assertRaises(HTTPException) as denied:
                await get_my_payment_order("not-a-uuid", user={"id": "user-a"})
        self.assertEqual(denied.exception.status_code, 404)
        engine.connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
