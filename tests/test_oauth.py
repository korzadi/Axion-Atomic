import os
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from api.oauth import configured, digest, begin, resolve_user, _validate_google_claims


class GoogleOidcClaimsTests(unittest.TestCase):
    def valid_claims(self):
        return {"aud": "google-client", "iss": "https://accounts.google.com", "nonce": "expected-nonce", "email_verified": True, "exp": 2000, "iat": 1900, "sub": "google-subject", "email": "person@example.com"}

    def test_accepts_valid_google_oidc_claims(self):
        _validate_google_claims(self.valid_claims(), nonce="expected-nonce", client_id="google-client", now=1950)

    def test_rejects_wrong_authorized_party_for_multiple_audiences(self):
        claims = self.valid_claims()
        claims["aud"] = ["google-client", "other-client"]
        claims["azp"] = "other-client"
        with self.assertRaises(ValueError):
            _validate_google_claims(claims, nonce="expected-nonce", client_id="google-client", now=1950)

    def test_rejects_future_issued_at(self):
        claims = self.valid_claims()
        claims["iat"] = 2100
        with self.assertRaises(ValueError):
            _validate_google_claims(claims, nonce="expected-nonce", client_id="google-client", now=1950)

    def test_rejects_unverified_email(self):
        claims = self.valid_claims()
        claims["email_verified"] = "true"
        with self.assertRaises(ValueError):
            _validate_google_claims(claims, nonce="expected-nonce", client_id="google-client", now=1950)


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


    def test_github_oauth_reads_axion_prefixed_environment_variables(self):
        with patch.dict(os.environ, {
            "AXION_GITHUB_CLIENT_ID": "github-client-id-test",
            "AXION_GITHUB_CLIENT_SECRET": "github-client-secret-test",
        }, clear=False):
            from api.config import Settings
            settings = Settings(_env_file=None)
        self.assertEqual(settings.github_oauth_client_id, "github-client-id-test")
        self.assertEqual(settings.github_oauth_client_secret, "github-client-secret-test")

    def test_oauth_start_rejects_missing_legal_consent_before_database_access(self):
        settings = Mock(google_oauth_client_id="id", google_oauth_client_secret="secret",
                        oauth_public_base_url="https://studio.example")
        with self.assertRaises(ValueError):
            begin(None, "google", settings, terms_accepted=False)

    def test_oauth_user_resolution_rejects_missing_legal_consent(self):
        with self.assertRaises(ValueError):
            resolve_user(None, "google", {}, terms_accepted=False)

    def test_state_is_stored_as_sha256_digest_not_plaintext(self):
        self.assertEqual(len(digest("random-oauth-state")), 64)
        self.assertNotEqual(digest("random-oauth-state"), "random-oauth-state")


if __name__ == "__main__":
    unittest.main()
