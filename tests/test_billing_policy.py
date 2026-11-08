"""Tests for deterministic, side-effect-free credit allocation."""
import unittest
from datetime import datetime, timedelta, timezone

from api.billing_policy import (
    CreditLot, InsufficientCredits, UsageUnavailable,
    credits_for_usage, plan_allocation,
)


class BillingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)

    def test_missing_counters_cannot_be_silently_charged_as_zero(self):
        with self.assertRaises(UsageUnavailable):
            credits_for_usage(None, 4)

    def test_input_and_output_weights_are_applied_independently(self):
        self.assertEqual(credits_for_usage(10, 5, input_weight=2, output_weight=3), 35)

    def test_consumption_priority_is_daily_then_subscription_then_purchased_fefo(self):
        lots = (
            CreditLot("later", 20, self.now + timedelta(days=10)),
            CreditLot("sooner", 20, self.now + timedelta(days=2)),
        )
        plan = plan_allocation(
            45, daily_free_available=5, subscription_available=10,
            purchased_lots=lots, purchased_fallback_allowed=True, now=self.now,
        )
        self.assertEqual(
            [(item.source, item.amount, item.lot_id) for item in plan.allocations],
            [("daily_free", 5, None), ("subscription", 10, None),
             ("purchased", 20, "sooner"), ("purchased", 10, "later")],
        )
        self.assertEqual(plan.remaining, 0)

    def test_purchased_fallback_is_disabled_by_default(self):
        with self.assertRaises(InsufficientCredits):
            plan_allocation(
                11, daily_free_available=5, subscription_available=5,
                purchased_lots=(CreditLot("lot", 100, self.now + timedelta(days=1)),),
                now=self.now,
            )

    def test_expired_lots_are_never_allocated(self):
        with self.assertRaises(InsufficientCredits):
            plan_allocation(
                1, daily_free_available=0, subscription_available=0,
                purchased_lots=(CreditLot("expired", 100, self.now),),
                purchased_fallback_allowed=True, now=self.now,
            )

    def test_failed_plan_does_not_mutate_input_lots(self):
        lot = CreditLot("lot", 2, self.now + timedelta(days=1))
        with self.assertRaises(InsufficientCredits):
            plan_allocation(
                3, daily_free_available=0, subscription_available=0,
                purchased_lots=(lot,), purchased_fallback_allowed=True, now=self.now,
            )
        self.assertEqual(lot.available, 2)

    def test_invalid_naive_expiry_is_rejected(self):
        with self.assertRaises(ValueError):
            plan_allocation(
                1, daily_free_available=0, subscription_available=0,
                purchased_lots=(CreditLot("lot", 1, datetime(2026, 11, 7)),),
                purchased_fallback_allowed=True, now=self.now,
            )


if __name__ == "__main__":
    unittest.main()


class FractionalWeightCreditTests(unittest.TestCase):
    def test_hundred_tokens_cost_exactly_one_credit(self):
        self.assertEqual(credits_for_usage(100, 0, input_weight=0.01, output_weight=0.01), 1)
        self.assertEqual(credits_for_usage(0, 100, input_weight=0.01, output_weight=0.01), 1)
        self.assertEqual(credits_for_usage(100, 100, input_weight=0.01, output_weight=0.01), 2)

    def test_partial_credits_round_up(self):
        self.assertEqual(credits_for_usage(150, 0, input_weight=0.01, output_weight=0.01), 2)
        self.assertEqual(credits_for_usage(0, 0, input_weight=0.01, output_weight=0.01), 0)

    def test_rejects_invalid_weights(self):
        for bad in (True, "0.01", -0.01, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                credits_for_usage(1, 1, input_weight=bad)
