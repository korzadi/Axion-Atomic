import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.readiness import auth_readiness


class AuthReadinessTests(unittest.TestCase):
    def test_readiness_is_blocked_when_authentication_is_disabled(self):
        settings = SimpleNamespace(
            auth_enabled=False,
            auth_cookie_secure=True,
            oauth_public_base_url="https://axyronatomic.com",
        )
        with (
            patch("api.readiness.settings", settings),
            patch("api.readiness.email_delivery_configured", return_value=True),
        ):
            report = auth_readiness()
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["checks"]["authentication_enabled"])
        self.assertFalse(report["checks"]["mfa_encryption_key"])

    def test_readiness_requires_all_auth_production_controls(self):
        settings = SimpleNamespace(
            auth_enabled=True,
            auth_cookie_secure=True,
            oauth_public_base_url="https://axyronatomic.com",
        )
        with (
            patch("api.readiness.settings", settings),
            patch("api.readiness.email_delivery_configured", return_value=True),
            patch("api.readiness.EnvironmentMfaKeyProvider.active_key", return_value=("key-v1", b"x" * 32)),
        ):
            report = auth_readiness()
        self.assertEqual(report["status"], "ready")
        self.assertTrue(all(report["checks"].values()))

    def test_readiness_never_exposes_mfa_key_material(self):
        settings = SimpleNamespace(
            auth_enabled=True,
            auth_cookie_secure=True,
            oauth_public_base_url="https://axyronatomic.com",
        )
        with (
            patch("api.readiness.settings", settings),
            patch("api.readiness.email_delivery_configured", return_value=True),
            patch("api.readiness.EnvironmentMfaKeyProvider.active_key", return_value=("private-key-id", b"secret" * 6)),
        ):
            report = auth_readiness()
        self.assertNotIn("private-key-id", repr(report))
        self.assertNotIn("secret", repr(report))


if __name__ == "__main__":
    unittest.main()
