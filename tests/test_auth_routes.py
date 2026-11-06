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

    def test_register_enforces_ip_rate_limit(self):
        from unittest.mock import Mock
        from fastapi import Request
        from api.auth_routes import register
        request = Mock(spec=Request)
        request.client.host = "198.51.100.10"
        with patch("api.auth_routes.settings.auth_enabled", True), \
             patch("api.auth_routes._enforce_rate_limit") as limiter, \
             patch("api.auth_routes.create_user"):
            import asyncio
            asyncio.run(register(
                RegisterRequest(email="new@example.com", password="StrongPassword123!", display_name="New"),
                request,
            ))
        limiter.assert_called_once()

    def test_login_enforces_ip_and_account_rate_limits(self):
        from unittest.mock import Mock
        from fastapi import Request, Response
        from api.auth_routes import login
        request = Mock(spec=Request)
        request.client.host = "198.51.100.11"
        request.headers.get.return_value = "test-agent"
        user = {"id": "user-1", "email": "test@example.com", "display_name": "Test"}
        with patch("api.auth_routes.settings.auth_enabled", True), \
             patch("api.auth_routes._enforce_rate_limit") as limiter, \
             patch("api.auth_routes.authenticate", return_value=(user, "session-token", "csrf-token")):
            import asyncio
            asyncio.run(login(
                LoginRequest(email="test@example.com", password="StrongPassword123!"),
                request, Response(),
            ))
        self.assertEqual(limiter.call_count, 2)
        self.assertEqual(limiter.call_args_list[1].kwargs["subject"], "test@example.com")


if __name__ == "__main__":
    unittest.main()
