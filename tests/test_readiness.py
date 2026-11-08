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

    def test_readiness_blocks_ledger_mode_without_dedicated_result_key(self):
        from api.billing_result_crypto import ResultEncryptionError

        settings = SimpleNamespace(
            auth_enabled=True,
            auth_cookie_secure=True,
            oauth_public_base_url="https://axyronatomic.com",
            billing_enforcement_enabled=True,
        )
        with (
            patch("api.readiness.settings", settings),
            patch("api.readiness.email_delivery_configured", return_value=True),
            patch("api.readiness.EnvironmentMfaKeyProvider.active_key", return_value=("mfa-v1", b"x" * 32)),
            patch("api.readiness.EnvironmentResultKeyProvider.active_key", side_effect=ResultEncryptionError("missing")),
        ):
            report = auth_readiness()
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["billing"]["mode"], "ledger")
        self.assertEqual(report["billing"]["chat_execution"], "integrated")
        self.assertEqual(report["billing"]["result_encryption_key"], "missing")

    def test_readiness_blocks_ledger_mode_until_runtime_attestation_is_configured(self):
        settings = SimpleNamespace(
            auth_enabled=True,
            auth_cookie_secure=True,
            oauth_public_base_url="https://axyronatomic.com",
            billing_enforcement_enabled=True,
        )
        with (
            patch("api.readiness.settings", settings),
            patch("api.readiness.email_delivery_configured", return_value=True),
            patch("api.readiness.EnvironmentMfaKeyProvider.active_key", return_value=("mfa-v1", b"x" * 32)),
            patch("api.readiness.EnvironmentResultKeyProvider.active_key", return_value=("result-v1", b"y" * 32)),
        ):
            report = auth_readiness()
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["billing"]["mode"], "ledger")
        self.assertEqual(report["billing"]["chat_execution"], "integrated")
        self.assertEqual(report["billing"]["runtime_attestation"], "missing")

    def test_readiness_allows_ledger_mode_with_key_and_runtime_manifest(self):
        settings = SimpleNamespace(
            auth_enabled=True,
            auth_cookie_secure=True,
            oauth_public_base_url="https://axyronatomic.com",
            billing_enforcement_enabled=True,
            billing_runtime_model_digest="sha256:" + "b" * 64,
            billing_runtime_template_sha256="a" * 64,
            billing_tokenizer_contract="qwen2_byte_fallback",
        )
        with (
            patch("api.readiness.settings", settings),
            patch("api.readiness.email_delivery_configured", return_value=True),
            patch("api.readiness.EnvironmentMfaKeyProvider.active_key", return_value=("mfa-v1", b"x" * 32)),
            patch("api.readiness.EnvironmentResultKeyProvider.active_key", return_value=("result-v1", b"y" * 32)),
        ):
            report = auth_readiness()
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["billing"]["runtime_attestation"], "configured")

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


    def test_readiness_rejects_non_https_or_ambiguous_public_origins(self):
        settings = SimpleNamespace(
            auth_enabled=True,
            auth_cookie_secure=True,
            oauth_public_base_url="http://axyronatomic.com",
        )
        invalid_origins = (
            "http://axyronatomic.com",
            "ftp://axyronatomic.com",
            "https://",
            "https://user:password@axyronatomic.com",
            "https://axyronatomic.com:invalid",
            "https://axyronatomic.com?redirect=http://other.example",
            "https://axyronatomic.com#fragment",
            "https://localhost",
            "https://127.0.0.1",
            "https://axyronatomic.com/auth/callback",
            "https://service.local",
            "https://axyronatomic",
        )
        with (
            patch("api.readiness.settings", settings),
            patch("api.readiness.email_delivery_configured", return_value=True),
            patch("api.readiness.EnvironmentMfaKeyProvider.active_key", return_value=("mfa-v1", b"x" * 32)),
        ):
            for origin in invalid_origins:
                with self.subTest(origin=origin):
                    settings.oauth_public_base_url = origin
                    report = auth_readiness()
                    self.assertEqual(report["status"], "blocked")
                    self.assertFalse(report["checks"]["public_https_origin"])



if __name__ == "__main__":
    unittest.main()


class LiveDependencyReadinessTests(unittest.TestCase):
    def test_readiness_requires_all_critical_live_dependencies(self):
        from api.readiness import combine_readiness_report
        auth = {"status": "ready", "checks": {"authentication_enabled": True}}
        deps = {
            "database": "ok", "ollama": "ok", "chat_model": "ok",
            "embedding_model": "ok", "qdrant": "unavailable", "redis": "degraded",
        }
        report = combine_readiness_report(auth, deps)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["dependencies"]["qdrant"], "unavailable")
        self.assertEqual(report["optional"]["redis"], "degraded")

    def test_readiness_is_ready_when_critical_dependencies_are_live(self):
        from api.readiness import combine_readiness_report
        auth = {"status": "ready", "checks": {"authentication_enabled": True}}
        deps = {
            "database": "ok", "ollama": "ok", "chat_model": "ok",
            "embedding_model": "ok", "qdrant": "ok", "redis": "degraded",
        }
        report = combine_readiness_report(auth, deps)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["optional"]["redis"], "degraded")
