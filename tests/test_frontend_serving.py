import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api.config import settings
from api.main import app


class AxionStudioServingTests(unittest.TestCase):
    def test_root_serves_axion_studio_entrypoint(self):
        with TestClient(app) as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("Tu asistente de IA", response.text)
        self.assertIn("Axyron Atomic", response.text)
        self.assertIn('data-open="reg"', response.text)

    def test_api_routes_keep_priority_over_frontend_mount(self):
        # AUTH_ENABLED remains closed by default; the API must not fall through
        # to the landing page or be shadowed by the frontend mount. Patch the
        # singleton explicitly so an ambient .env with AUTH_ENABLED=true cannot
        # change the contract under test.
        with mock.patch.object(settings, "auth_enabled", False):
            with TestClient(app) as client:
                response = client.get("/auth/me")

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("<!doctype html>", response.text.lower())


if __name__ == "__main__":
    unittest.main()
