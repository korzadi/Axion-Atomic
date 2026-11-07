import asyncio
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException, Request, Response

from api.auth_routes import _require_auth_feature, _authenticated_user
from api.schemas import LoginRequest, RegisterRequest


class AuthRouteGateTests(unittest.TestCase):
    def test_auth_routes_fail_closed_by_default(self):
        with patch("api.auth_routes.settings.auth_enabled", False):
            with self.assertRaises(HTTPException) as raised:
                _require_auth_feature()
            self.assertEqual(raised.exception.status_code, 503)

    def test_authenticated_route_checks_global_gate_before_session(self):
        with patch("api.auth_routes.settings.auth_enabled", False), patch("api.auth_routes.current_user") as current:
            with self.assertRaises(HTTPException) as raised:
                _authenticated_user()
        self.assertEqual(raised.exception.status_code, 503)
        current.assert_not_called()

    def test_auth_routes_can_pass_gate_only_when_explicitly_enabled(self):
        with patch("api.auth_routes.settings.auth_enabled", True):
            _require_auth_feature()

    def test_registration_password_has_minimum_length(self):
        with self.assertRaises(ValueError):
            RegisterRequest(email="user@example.com", password="short", display_name="User")

    def test_login_request_is_bounded(self):
        request = LoginRequest(email="user@example.com", password="a" * 1024)
        self.assertEqual(len(request.password), 1024)

    def test_register_enforces_ip_rate_limit(self):
        from api.auth_routes import register
        request = Mock(spec=Request)
        request.client.host = "198.51.100.10"
        with patch("api.auth_routes.settings.auth_enabled", True):
            with patch("api.auth_routes._enforce_rate_limit") as limiter:
                with patch("api.auth_routes.email_delivery_configured", return_value=True):
                    with patch("api.auth_routes.settings.oauth_public_base_url", "https://axion.example"):
                        with patch("api.auth_routes.create_user", return_value=None):
                            asyncio.run(register(
                                RegisterRequest(email="new@example.com", password="StrongPassword123!", display_name="New", terms_accepted=True),
                                request,
                            ))
        self.assertEqual(limiter.call_count, 2)

    def test_oauth_callback_rejects_mismatched_browser_state_without_server_error(self):
        from api.auth_routes import oauth_callback
        request = Mock(spec=Request)
        request.client.host = "198.51.100.13"
        with patch("api.auth_routes.settings.auth_enabled", True):
            with patch("api.auth_routes._enforce_rate_limit"):
                response = asyncio.run(oauth_callback(
                    "google", request, code="authorization-code", state="provider-state",
                    browser_state="different-browser-state",
                ))
        self.assertEqual(response.status_code, 303)
        self.assertIn("oauth_error=cancelled", response.headers["location"])

    def test_oauth_callback_enforces_provider_ip_rate_limit(self):
        from api.auth_routes import oauth_callback
        request = Mock(spec=Request)
        request.client.host = "198.51.100.12"
        with patch("api.auth_routes.settings.auth_enabled", True):
            with patch("api.auth_routes._enforce_rate_limit") as limiter:
                response = asyncio.run(oauth_callback(
                    "github", request, code="authorization-code", state="provider-state",
                    browser_state="different-browser-state",
                ))
        self.assertEqual(response.status_code, 303)
        limiter.assert_called_once()
        self.assertEqual(limiter.call_args.kwargs["namespace"], "auth:oauth:callback:github")
        self.assertEqual(limiter.call_args.kwargs["limit"], 20)

    def test_login_enforces_ip_and_account_rate_limits_without_mfa(self):
        from api.auth_routes import login
        request = Mock(spec=Request)
        request.client.host = "198.51.100.11"
        request.headers.get.return_value = "test-agent"
        user = {"id": "user-1", "email": "test@example.com", "display_name": "Test"}
        response = Response()
        with patch("api.auth_routes.settings.auth_enabled", True):
            with patch("api.auth_routes._enforce_rate_limit") as limiter:
                with patch("api.auth_routes.verify_credentials", return_value=user):
                    with patch("api.auth_routes.is_mfa_enabled", return_value=False):
                        with patch("api.auth_routes.create_session", return_value=("session-token", "csrf-token")):
                            result = asyncio.run(login(
                                LoginRequest(email="test@example.com", password="StrongPassword123!"),
                                request, response,
                            ))
        self.assertEqual(limiter.call_count, 2)
        self.assertEqual(limiter.call_args_list[1].kwargs["subject"], "test@example.com")
        self.assertEqual(result["user"], user)
        self.assertIn("axion_session=session-token", response.headers["set-cookie"])

    def test_password_login_returns_challenge_without_creating_session_when_mfa_enabled(self):
        from api.auth_routes import login
        request = Mock(spec=Request)
        request.client.host = "198.51.100.14"
        request.headers.get.return_value = "test-agent"
        user = {"id": "user-2", "email": "mfa@example.com", "display_name": "MFA"}
        with patch("api.auth_routes.settings.auth_enabled", True):
            with patch("api.auth_routes._enforce_rate_limit"):
                with patch("api.auth_routes.verify_credentials", return_value=user):
                    with patch("api.auth_routes.is_mfa_enabled", return_value=True):
                        with patch("api.auth_routes.issue_login_challenge", return_value="opaque-challenge") as issue:
                            with patch("api.auth_routes.create_session") as create:
                                result = asyncio.run(login(
                                    LoginRequest(email="mfa@example.com", password="StrongPassword123!"),
                                    request, Response(),
                                ))
        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.body, b'{"mfa_required":true,"challenge_token":"opaque-challenge","expires_in":300}')
        issue.assert_called_once()
        create.assert_not_called()

    def test_oauth_provider_discovery_exposes_only_availability_flags(self):
        from api.auth_routes import oauth_providers
        with patch("api.auth_routes.configured", side_effect=lambda settings, provider: provider == "google"):
            result = asyncio.run(oauth_providers())
        self.assertEqual(result, {"google": True, "github": False})
        self.assertTrue(all(isinstance(value, bool) for value in result.values()))
        self.assertNotIn("client_id", result)
        self.assertNotIn("client_secret", result)


if __name__ == "__main__":
    unittest.main()
