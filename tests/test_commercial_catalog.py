import unittest

from api.commercial_catalog import public_catalog


class CommercialCatalogTests(unittest.TestCase):
    def test_catalog_uses_final_axyron_brand(self):
        catalog = public_catalog()
        self.assertIn("AXYRON ATOMIC", catalog["models"][0]["description"])
        self.assertNotIn("AXION ATOMIC", catalog["models"][0]["description"])

    def test_only_atomic_code_is_marked_as_billing_candidate(self):
        catalog = public_catalog()
        self.assertEqual([model["code"] for model in catalog["models"]], ["atomic-code"])
        self.assertTrue(catalog["models"][0]["billing_candidate"])
        self.assertFalse(catalog["models"][0]["billing_enabled"])

    def test_catalog_is_preview_only_and_checkout_is_closed(self):
        catalog = public_catalog()
        self.assertEqual(catalog["status"], "preview_only")
        self.assertFalse(catalog["checkout_enabled"])
        self.assertIsNone(catalog["payment_provider"])

    def test_no_unapproved_prices_plans_or_credit_packages_are_published(self):
        catalog = public_catalog()
        self.assertEqual(catalog["plans"], [])
        self.assertEqual(catalog["credit_packages"], [])

    def test_catalog_is_detached_and_cannot_mutate_static_model_definition(self):
        first = public_catalog()
        first["models"][0]["billing_enabled"] = True
        second = public_catalog()
        self.assertFalse(second["models"][0]["billing_enabled"])


if __name__ == "__main__":
    unittest.main()
