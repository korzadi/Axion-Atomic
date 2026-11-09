import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class PublicCatalogRouteTests(unittest.TestCase):
    def test_public_catalog_is_readable_without_authentication(self):
        client = TestClient(app)
        response = client.get("/billing/catalog")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "active")

    def test_only_atomic_code_is_exposed_as_billing_candidate(self):
        client = TestClient(app)
        body = client.get("/billing/catalog").json()
        self.assertEqual([model["code"] for model in body["models"]], ["atomic-code"])
        self.assertTrue(body["models"][0]["billing_candidate"])

    def test_approved_plans_are_published(self):
        client = TestClient(app)
        body = client.get("/billing/catalog").json()
        self.assertEqual([p["code"] for p in body["plans"]], ["starter_300", "plus_750", "pro_1700", "studio_3600"])
        self.assertEqual(body["credit_packages"], [])

    def test_checkout_stays_closed_while_qvapay_is_disabled(self):
        client = TestClient(app)
        body = client.get("/billing/catalog").json()
        self.assertFalse(body["checkout_enabled"])
        self.assertIsNone(body["payment_provider"])

    def test_checkout_opens_with_qvapay_enabled(self):
        client = TestClient(app)
        with patch("api.commercial_catalog.settings.qvapay_enabled", True):
            body = client.get("/billing/catalog").json()
        self.assertTrue(body["checkout_enabled"])
        self.assertEqual(body["payment_provider"], "qvapay_lightning")


if __name__ == "__main__":
    unittest.main()
