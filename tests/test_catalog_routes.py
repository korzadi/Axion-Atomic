import unittest

from fastapi.testclient import TestClient

from api.main import app


class PublicCatalogRouteTests(unittest.TestCase):
    def test_public_catalog_is_readable_without_authentication(self):
        client = TestClient(app)
        response = client.get("/billing/catalog")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "preview_only")
        self.assertFalse(body["checkout_enabled"])
        self.assertIsNone(body["payment_provider"])

    def test_only_atomic_code_is_exposed_as_billing_candidate(self):
        client = TestClient(app)
        body = client.get("/billing/catalog").json()
        self.assertEqual([model["code"] for model in body["models"]], ["atomic-code"])
        self.assertTrue(body["models"][0]["billing_candidate"])
        self.assertFalse(body["models"][0]["billing_enabled"])

    def test_unapproved_commercial_items_are_not_exposed(self):
        client = TestClient(app)
        body = client.get("/billing/catalog").json()
        self.assertEqual(body["plans"], [])
        self.assertEqual(body["credit_packages"], [])


if __name__ == "__main__":
    unittest.main()
