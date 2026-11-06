import asyncio
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from api.auth_recovery_routes import verify_email, resend_verification, forgot_password, reset_password
from api.schemas import EmailTokenRequest, EmailAddressRequest, PasswordResetRequest


class AuthRecoveryThreadpoolTests(unittest.TestCase):
    def request(self):
        request = SimpleNamespace(client=SimpleNamespace(host="198.51.100.20"))
        return request

    def test_verify_email_moves_rate_limit_and_token_consumption_to_threadpool(self):
        calls = []

        async def threadpool(func, *args, **kwargs):
            calls.append(func.__name__)
            return func(*args, **kwargs)

        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=threadpool), \
             patch("api.auth_recovery_routes._limit"), \
             patch("api.auth_recovery_routes.consume_email_verification_token", return_value=True):
            result = asyncio.run(verify_email(EmailTokenRequest(token="x" * 32), self.request()))
        self.assertEqual(result["status"], "verified")
        self.assertEqual(calls, ["_limit", "consume_email_verification_token"])

    def test_resend_verification_runs_database_and_email_helper_off_loop(self):
        calls = []

        async def threadpool(func, *args, **kwargs):
            calls.append(func.__name__)
            return func(*args, **kwargs)

        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=False), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=threadpool), \
             patch("api.auth_recovery_routes._limit"):
            result = asyncio.run(resend_verification(EmailAddressRequest(email="user@example.com"), self.request()))
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(calls, ["_limit", "_limit"])

    def test_forgot_password_runs_database_and_email_helper_off_loop(self):
        calls = []

        async def threadpool(func, *args, **kwargs):
            calls.append(func.__name__)
            return func(*args, **kwargs)

        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=False), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=threadpool), \
             patch("api.auth_recovery_routes._limit"):
            result = asyncio.run(forgot_password(EmailAddressRequest(email="user@example.com"), self.request()))
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(calls, ["_limit", "_limit"])

    def test_password_reset_runs_rate_limit_and_token_consumption_off_loop(self):
        calls = []

        async def threadpool(func, *args, **kwargs):
            calls.append(func.__name__)
            return func(*args, **kwargs)

        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=threadpool), \
             patch("api.auth_recovery_routes._limit"), \
             patch("api.auth_recovery_routes.consume_password_reset_token", return_value=True):
            result = asyncio.run(reset_password(
                PasswordResetRequest(token="x" * 32, new_password="StrongPassword123!"),
                self.request(),
            ))
        self.assertEqual(result["status"], "password_changed")
        self.assertEqual(calls, ["_limit", "consume_password_reset_token"])


if __name__ == "__main__":
    unittest.main()
