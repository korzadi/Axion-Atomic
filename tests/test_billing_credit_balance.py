import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from api.payment_routes import get_my_credit_balance


class BillingCreditBalanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_balance_uses_real_quota_lot_and_ledger_rows(self):
        quota = [
            {
                "quota_kind": "daily_free",
                "granted_credits": 1000,
                "reserved_credits": 100,
                "consumed_credits": 200,
                "available_credits": 700,
            }
        ]
        lots = {
            "lot_count": 2,
            "granted_credits": 5000,
            "available_credits": 4000,
            "reserved_credits": 300,
            "consumed_credits": 700,
        }
        ledger = [{
            "event_type": "consume",
            "available_delta": 0,
            "reserved_delta": -50,
            "consumed_delta": 50,
            "reason": "Liquidación de uso medido",
            "created_at": datetime(2026, 11, 7, tzinfo=timezone.utc),
        }]

        def result(rows=None, one=None):
            mappings = MagicMock()
            mappings.all.return_value = rows
            mappings.one.return_value = one
            value = MagicMock()
            value.mappings.return_value = mappings
            return value

        connection = MagicMock()
        connection.execute.side_effect = [
            result(rows=quota),
            result(one=lots),
            result(rows=ledger),
        ]
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection

        with (
            patch("api.payment_routes.engine", engine),
            patch("api.payment_routes._limit_reads"),
        ):
            response = await get_my_credit_balance({"id": "user-a"})

        self.assertTrue(response["provisioned"])
        self.assertEqual(response["totals"], {
            "available": 4700,
            "reserved": 400,
            "consumed": 900,
        })
        self.assertEqual(response["quotas"], quota)
        self.assertEqual(response["purchased_lots"]["count"], 2)
        self.assertEqual(response["recent_ledger"], ledger)

    async def test_unprovisioned_user_is_not_given_synthetic_credits(self):
        empty_lots = {
            "lot_count": 0,
            "granted_credits": 0,
            "available_credits": 0,
            "reserved_credits": 0,
            "consumed_credits": 0,
        }

        def result(rows=None, one=None):
            mappings = MagicMock()
            mappings.all.return_value = rows
            mappings.one.return_value = one
            value = MagicMock()
            value.mappings.return_value = mappings
            return value

        connection = MagicMock()
        connection.execute.side_effect = [
            result(rows=[]),
            result(one=empty_lots),
            result(rows=[]),
        ]
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection

        with (
            patch("api.payment_routes.engine", engine),
            patch("api.payment_routes._limit_reads"),
        ):
            response = await get_my_credit_balance({"id": "user-new"})

        self.assertFalse(response["provisioned"])
        self.assertEqual(response["totals"], {"available": 0, "reserved": 0, "consumed": 0})
        self.assertEqual(response["purchased_lots"]["granted"], 0)


if __name__ == "__main__":
    unittest.main()
