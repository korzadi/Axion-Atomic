import os
import unittest
from unittest.mock import patch

from api.config import Settings


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


if __name__ == "__main__":
    unittest.main()
