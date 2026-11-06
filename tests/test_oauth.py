import unittest
from unittest.mock import Mock
from api.oauth import configured, digest


class OAuthConfigurationTests(unittest.TestCase):
    def test_google_requires_client_id_secret_and_public_url(self):
        settings = Mock(google_oauth_client_id="id", google_oauth_client_secret="secret",
                        github_oauth_client_id=None, github_oauth_client_secret=None,
                        oauth_public_base_url="https://studio.example")
        self.assertTrue(configured(settings, "google"))
        self.assertFalse(configured(settings, "github"))

    def test_provider_is_not_enabled_without_public_callback_url(self):
        settings = Mock(google_oauth_client_id="id", google_oauth_client_secret="secret",
                        github_oauth_client_id="id", github_oauth_client_secret="secret",
                        oauth_public_base_url=None)
        self.assertFalse(configured(settings, "google"))
        self.assertFalse(configured(settings, "github"))

    def test_state_is_stored_as_sha256_digest_not_plaintext(self):
        self.assertEqual(len(digest("random-oauth-state")), 64)
        self.assertNotEqual(digest("random-oauth-state"), "random-oauth-state")


if __name__ == "__main__":
    unittest.main()
