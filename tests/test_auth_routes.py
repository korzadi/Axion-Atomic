import unittest
from unittest.mock import patch
from fastapi import HTTPException

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


if __name__ == "__main__":
    unittest.main()


    def test_email_verification_request_is_bounded(self):
        from api.schemas import EmailVerificationRequest
        request = EmailVerificationRequest(token="x" * 256)
        self.assertEqual(len(request.token), 256)

    def test_email_verification_rejects_short_token(self):
        from api.schemas import EmailVerificationRequest
        with self.assertRaises(ValueError):
            EmailVerificationRequest(token="short")

    def test_verify_email_route_requires_auth_feature_gate(self):
        from api.auth_routes import verify_email
        from api.schemas import EmailVerificationRequest
        with patch("api.auth_routes.settings.auth_enabled", False):
            with self.assertRaises(HTTPException) as raised:
                import asyncio
                asyncio.run(verify_email(EmailVerificationRequest(token="x" * 32)))
        self.assertEqual(raised.exception.status_code, 503)
