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

    def test_registration_consent_requires_explicit_json_boolean(self):
        for value in (1, 0, "true", "false", "yes"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    RegisterRequest(
                        email="user@example.com",
                        password="StrongPassword123!",
                        display_name="User",
                        terms_accepted=value,
                    )

        accepted = RegisterRequest(
            email="user@example.com",
            password="StrongPassword123!",
            display_name="User",
            terms_accepted=True,
        )
        self.assertIs(accepted.terms_accepted, True)

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
        session_cookie = next(cookie for cookie in response.headers.getlist("set-cookie") if cookie.startswith("axion_session="))
        self.assertIn("httponly", session_cookie.lower())

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

    def test_logout_revokes_session_and_clears_both_auth_cookies(self):
        from api.auth_routes import logout
        request = Mock(spec=Request)
        response = Response()
        user = {"id": "user-logout", "email": "logout@example.com"}
        with patch("api.auth_routes.settings.auth_enabled", True), \
             patch("api.auth_routes.revoke_session") as revoke:
            result = asyncio.run(logout(
                request=request, response=response, user=user,
                axion_session="opaque-session-token",
            ))
        revoke.assert_called_once_with("opaque-session-token")
        self.assertEqual(result, {"status": "logged_out"})
        cookies = response.headers.getlist("set-cookie")
        self.assertTrue(any(cookie.startswith("axion_session=") and "Max-Age=0" in cookie for cookie in cookies))
        self.assertTrue(any(cookie.startswith("axion_csrf=") and "Max-Age=0" in cookie for cookie in cookies))

    def test_registration_never_returns_email_verification_token(self):
        from types import SimpleNamespace
        from api.auth_routes import register
        request = Mock(spec=Request)
        request.client.host = "198.51.100.21"
        secret_token = "verification-secret-token-never-return-this"
        with patch("api.auth_routes.settings.auth_enabled", True), \
             patch("api.auth_routes._enforce_rate_limit"), \
             patch("api.auth_routes.email_delivery_configured", return_value=True), \
             patch("api.auth_routes.settings.oauth_public_base_url", "https://axion.example"), \
             patch("api.auth_routes.create_user", return_value="new-user-id"), \
             patch("api.auth_routes.issue_email_verification_token", return_value=SimpleNamespace(token=secret_token)), \
             patch("api.auth_routes.send_verification_email") as send_email:
            result = asyncio.run(register(
                RegisterRequest(email="new@example.com", password="StrongPassword123!", display_name="New", terms_accepted=True),
                request,
            ))
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.kwargs["token"], secret_token)
        self.assertEqual(result["status"], "pending_verification")
        self.assertNotIn(secret_token, str(result))
        self.assertNotIn("token", result)

    def test_registration_email_failure_keeps_generic_response_and_hides_token(self):
        from types import SimpleNamespace
        from api.auth_routes import register
        request = Mock(spec=Request)
        request.client.host = "198.51.100.22"
        secret_token = "verification-secret-token-never-return-this"
        with patch("api.auth_routes.settings.auth_enabled", True), \
             patch("api.auth_routes._enforce_rate_limit"), \
             patch("api.auth_routes.email_delivery_configured", return_value=True), \
             patch("api.auth_routes.settings.oauth_public_base_url", "https://axion.example"), \
             patch("api.auth_routes.create_user", return_value="new-user-id"), \
             patch("api.auth_routes.issue_email_verification_token", return_value=SimpleNamespace(token=secret_token)), \
             patch("api.auth_routes.send_verification_email", side_effect=RuntimeError("mail transport failure")):
            result = asyncio.run(register(
                RegisterRequest(email="new@example.com", password="StrongPassword123!", display_name="New", terms_accepted=True),
                request,
            ))
        self.assertEqual(result["status"], "pending_verification")
        self.assertNotIn(secret_token, str(result))
        self.assertNotIn("token", result)

    def test_recovery_endpoints_return_generic_responses_even_when_delivery_fails(self):
        from api.auth_recovery_routes import resend_verification, forgot_password
        from api.schemas import EmailAddressRequest
        request = Mock(spec=Request)
        request.client.host = "198.51.100.31"
        req = EmailAddressRequest(email="unknown@example.com")
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes._limit"), \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=True), \
             patch("api.auth_recovery_routes.settings.oauth_public_base_url", "https://axion.example"), \
             patch("api.auth_recovery_routes._resend_verification_if_pending", side_effect=RuntimeError("mail unavailable")), \
             patch("api.auth_recovery_routes._send_password_reset_if_active", side_effect=RuntimeError("mail unavailable")):
            resend = asyncio.run(resend_verification(req, request))
            forgot = asyncio.run(forgot_password(req, request))
        self.assertEqual(resend["status"], "accepted")
        self.assertEqual(forgot["status"], "accepted")
        self.assertIn("Si existe una cuenta pendiente", resend["message"])
        self.assertIn("Si existe una cuenta activa", forgot["message"])

    def test_recovery_endpoints_do_not_reveal_whether_email_delivery_is_configured(self):
        from api.auth_recovery_routes import resend_verification, forgot_password
        from api.schemas import EmailAddressRequest
        request = Mock(spec=Request)
        request.client.host = "198.51.100.32"
        req = EmailAddressRequest(email="account@example.com")
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes._limit"), \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=False), \
             patch("api.auth_recovery_routes.settings.oauth_public_base_url", None):
            resend = asyncio.run(resend_verification(req, request))
            forgot = asyncio.run(forgot_password(req, request))
        self.assertEqual(resend["status"], "accepted")
        self.assertEqual(forgot["status"], "accepted")
        self.assertIn("Si existe una cuenta pendiente", resend["message"])
        self.assertIn("Si existe una cuenta activa", forgot["message"])
        self.assertNotIn("not configured", resend["message"].lower())
        self.assertNotIn("not configured", forgot["message"].lower())

    def test_recovery_endpoints_apply_ip_and_normalized_account_rate_limits(self):
        from api.auth_recovery_routes import resend_verification, forgot_password
        from api.schemas import EmailAddressRequest
        request = Mock(spec=Request)
        request.client.host = "198.51.100.33"
        req = EmailAddressRequest(email="  Person@Example.com ")
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes._limit") as limiter, \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=False):
            asyncio.run(resend_verification(req, request))
            asyncio.run(forgot_password(req, request))
        self.assertEqual(limiter.call_count, 4)
        calls = limiter.call_args_list
        self.assertEqual(calls[0].args[1], "auth:verify-resend:ip")
        self.assertEqual(calls[1].args[1], "auth:verify-resend:account")
        self.assertEqual(calls[1].args[4], "person@example.com")
        self.assertEqual(calls[2].args[1], "auth:password-forgot:ip")
        self.assertEqual(calls[3].args[1], "auth:password-forgot:account")
        self.assertEqual(calls[3].args[4], "person@example.com")

    def test_recovery_rate_limit_rejection_stops_processing_with_429(self):
        from api.auth_recovery_routes import resend_verification
        from api.schemas import EmailAddressRequest
        request = Mock(spec=Request)
        request.client.host = "198.51.100.34"
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes._limit", side_effect=HTTPException(status_code=429, detail="Demasiadas solicitudes")) as limiter, \
             patch("api.auth_recovery_routes._resend_verification_if_pending") as delivery:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(resend_verification(
                    EmailAddressRequest(email="person@example.com"), request,
                ))
        self.assertEqual(raised.exception.status_code, 429)
        limiter.assert_called_once()
        delivery.assert_not_called()

    def test_oauth_provider_discovery_exposes_only_availability_flags(self):
        from api.auth_routes import oauth_providers
        with patch("api.auth_routes.configured", side_effect=lambda settings, provider: provider == "google"):
            result = asyncio.run(oauth_providers())
        self.assertEqual(result, {"google": True, "github": False})
        self.assertTrue(all(isinstance(value, bool) for value in result.values()))
        self.assertNotIn("client_id", result)
        self.assertNotIn("client_secret", result)


class RecoveryRateLimitFailureTests(unittest.TestCase):
    def test_recovery_rate_limit_fails_closed_when_storage_is_unavailable(self):
        from datetime import timedelta
        from api.auth_recovery_routes import _limit
        request = Mock(spec=Request)
        request.client.host = "198.51.100.40"
        with patch("api.auth_recovery_routes.consume_rate_limit", side_effect=RuntimeError("database unavailable")):
            with self.assertRaises(HTTPException) as raised:
                _limit(request, "auth:verify-resend:ip", 10, timedelta(minutes=10))
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "Protección temporalmente no disponible")

    def test_recovery_rate_limit_returns_retry_after_header(self):
        from datetime import timedelta
        from api.auth_recovery_routes import _limit
        from api.rate_limit import RateLimitDecision
        request = Mock(spec=Request)
        request.client.host = "198.51.100.41"
        decision = RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=137)
        with patch("api.auth_recovery_routes.consume_rate_limit", return_value=decision):
            with self.assertRaises(HTTPException) as raised:
                _limit(request, "auth:password-forgot:ip", 10, timedelta(minutes=10))
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.headers["Retry-After"], "137")

    def test_recovery_rate_limit_rejects_missing_client_origin(self):
        from datetime import timedelta
        from api.auth_recovery_routes import _limit
        request = Mock(spec=Request)
        request.client = None
        with patch("api.auth_recovery_routes.consume_rate_limit") as consume:
            with self.assertRaises(HTTPException) as raised:
                _limit(request, "auth:verify-resend:ip", 10, timedelta(minutes=10))
        self.assertEqual(raised.exception.status_code, 503)
        consume.assert_not_called()


if __name__ == "__main__":
    unittest.main()
