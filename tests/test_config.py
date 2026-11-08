import os
import unittest
from unittest.mock import patch

from api.config import Settings, is_public_https_origin


class EnvironmentAliasTests(unittest.TestCase):
    def load_settings(self, values):
        with patch.dict(os.environ, values, clear=True):
            return Settings(_env_file=None)

    def test_google_uses_github_configured_variable_names(self):
        settings = self.load_settings({
            "GOOGLE_CLIENT_ID": "google-client-id",
            "GOOGLE_CLIENT_SECRET": "google-client-secret",
        })
        self.assertEqual(settings.google_oauth_client_id, "google-client-id")
        self.assertEqual(settings.google_oauth_client_secret, "google-client-secret")

    def test_google_accepts_previous_oauth_prefixed_aliases(self):
        settings = self.load_settings({
            "GOOGLE_OAUTH_CLIENT_ID": "legacy-google-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "legacy-google-secret",
        })
        self.assertEqual(settings.google_oauth_client_id, "legacy-google-id")
        self.assertEqual(settings.google_oauth_client_secret, "legacy-google-secret")

    def test_github_accepts_current_and_previous_variable_names(self):
        current = self.load_settings({
            "AXYRON_GITHUB_CLIENT_ID": "current-id",
            "AXYRON_GITHUB_CLIENT_SECRET": "current-secret",
        })
        self.assertEqual(current.github_oauth_client_id, "current-id")
        self.assertEqual(current.github_oauth_client_secret, "current-secret")

        legacy = self.load_settings({
            "AXION_GITHUB_CLIENT_ID": "legacy-id",
            "AXION_GITHUB_CLIENT_SECRET": "legacy-secret",
        })
        self.assertEqual(legacy.github_oauth_client_id, "legacy-id")
        self.assertEqual(legacy.github_oauth_client_secret, "legacy-secret")

    def test_smtp_user_and_smtp_username_are_compatible(self):
        current = self.load_settings({"SMTP_USERNAME": "smtp-current"})
        legacy = self.load_settings({"SMTP_USER": "smtp-legacy"})
        self.assertEqual(current.smtp_username, "smtp-current")
        self.assertEqual(legacy.smtp_username, "smtp-legacy")


    def test_qdrant_url_uses_shared_public_https_contract(self):
        settings = self.load_settings({
            "QDRANT_URL": "HTTPS://CLUSTER.QDRANT.IO:8443/",
        })
        self.assertEqual(settings.qdrant_url, "HTTPS://CLUSTER.QDRANT.IO:8443/")

    def test_qdrant_url_rejects_invalid_public_origins(self):
        invalid_urls = (
            "http://cluster.qdrant.io",
            "https://127.0.0.1",
            "https://cluster.qdrant.io:invalid",
            "https://cluster.qdrant.io:",
            "https://cluster.qdrant.io/path",
            "https://cluster..qdrant.io",
            "https://cluster.qdrant.io..",
            "https://-cluster.qdrant.io",
            "https://cluster.qdrant.io?token=hidden",
            "https://user:password@cluster.qdrant.io",
            "https://cluster.qdrant.io\n.attacker.example",
            "https://cluster.qdrant.io\t.attacker.example",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.load_settings({"QDRANT_URL": url})

    def test_oauth_origin_uses_shared_public_https_contract(self):
        settings = self.load_settings({
            "OAUTH_PUBLIC_BASE_URL": "HTTPS://AXYRONATOMIC.COM.:8443/",
        })
        self.assertEqual(settings.oauth_public_base_url, "https://axyronatomic.com:8443")
        self.assertTrue(is_public_https_origin(settings.oauth_public_base_url))

    def test_oauth_origin_rejects_malformed_dns_hostnames(self):
        invalid_origins = (
            "https://a..example.com",
            "https://-bad.example.com",
            "https://bad-.example.com",
            "https://example.com:",
            "https://example.com..",
            "https://bad_host.example.com",
            "https://a" + "x" * 64 + ".example.com",
            "https://axyronatomic.com\n.attacker.example",
            "https://axyronatomic.com\t.attacker.example",
        )
        for origin in invalid_origins:
            with self.subTest(origin=origin):
                self.assertFalse(is_public_https_origin(origin))
                with self.assertRaises(ValueError):
                    self.load_settings({"OAUTH_PUBLIC_BASE_URL": origin})


if __name__ == "__main__":
    unittest.main()
