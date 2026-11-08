import unittest
from unittest.mock import patch

from api.commercial_catalog import plan_for_code, public_catalog


class CommercialCatalogTests(unittest.TestCase):
    def test_catalog_uses_final_axyron_brand(self):
        catalog = public_catalog()
        self.assertIn("AXYRON ATOMIC", catalog["models"][0]["description"])
        self.assertNotIn("AXION ATOMIC", catalog["models"][0]["description"])

    def test_only_atomic_code_is_marked_as_billing_candidate(self):
        catalog = public_catalog()
        self.assertEqual([model["code"] for model in catalog["models"]], ["atomic-code"])
        self.assertTrue(catalog["models"][0]["billing_candidate"])

    def test_catalog_is_active_with_approved_plans(self):
        catalog = public_catalog()
        self.assertEqual(catalog["status"], "active")
        self.assertEqual(
            [(p["code"], p["credits"], p["price_minor"]) for p in catalog["plans"]],
            [
                ("starter_300", 300, 499),
                ("plus_750", 750, 999),
                ("pro_1700", 1700, 1999),
                ("studio_3600", 3600, 3999),
            ],
        )
        self.assertTrue(all(p["one_time"] for p in catalog["plans"]))
        self.assertTrue(all(p["currency"] == "USD" for p in catalog["plans"]))
        self.assertEqual(catalog["free_credits_on_verify"], 50)
        self.assertEqual(catalog["credit_packages"], [])

    def test_checkout_stays_closed_while_qvapay_is_disabled(self):
        catalog = public_catalog()
        self.assertFalse(catalog["checkout_enabled"])
        self.assertIsNone(catalog["payment_provider"])

    def test_checkout_opens_with_qvapay_enabled(self):
        with patch("api.commercial_catalog.settings.qvapay_enabled", True):
            catalog = public_catalog()
        self.assertTrue(catalog["checkout_enabled"])
        self.assertEqual(catalog["payment_provider"], "qvapay_lightning")

    def test_model_billing_enabled_follows_enforcement_flag(self):
        with patch("api.commercial_catalog.settings.billing_enforcement_enabled", True):
            catalog = public_catalog()
        self.assertTrue(catalog["models"][0]["billing_enabled"])

    def test_plan_for_code_returns_exact_approved_values(self):
        plan = plan_for_code("pro_1700")
        self.assertEqual(plan["credits"], 1700)
        self.assertEqual(plan["price_minor"], 1999)
        self.assertIsNone(plan_for_code("nonexistent_plan"))

    def test_catalog_is_detached_and_cannot_mutate_static_definition(self):
        first = public_catalog()
        first["models"][0]["billing_enabled"] = True
        first["plans"][0]["credits"] = 999999
        second = public_catalog()
        self.assertNotEqual(second["plans"][0]["credits"], 999999)


if __name__ == "__main__":
    unittest.main()
