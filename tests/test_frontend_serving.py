import unittest

from fastapi.testclient import TestClient

from api.main import app


class AxionStudioServingTests(unittest.TestCase):
    def test_root_serves_axion_studio_entrypoint(self):
        with TestClient(app) as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("AXION STUDIO", response.text)
        self.assertIn('data-open="register"', response.text)

    def test_api_routes_keep_priority_over_frontend_mount(self):
        with TestClient(app) as client:
            response = client.get("/auth/me")

        # AUTH_ENABLED remains closed by default; the API must not fall through
        # to index.html or be shadowed by the frontend mount.
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("<!doctype html>", response.text.lower())


if __name__ == "__main__":
    unittest.main()
