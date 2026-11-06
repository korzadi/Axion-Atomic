import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.auth_recovery_routes import verify_email, resend_verification, forgot_password, reset_password, _limit
from api.schemas import EmailTokenRequest, EmailAddressRequest, PasswordResetRequest


class AuthRecoveryThreadpoolTests(unittest.TestCase):
    def request(self):
        return SimpleNamespace(client=SimpleNamespace(host="198.51.100.20"))

    def threadpool_runner(self, calls):
        async def run(func, *args, **kwargs):
            calls.append(func)
            return func(*args, **kwargs)
        return run

    def rate_limit_decision(self):
        return SimpleNamespace(allowed=True, retry_after_seconds=0)

    def test_verify_email_moves_rate_limit_and_token_consumption_to_threadpool(self):
        calls = []
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=self.threadpool_runner(calls)), \
             patch("api.auth_recovery_routes.consume_rate_limit", return_value=self.rate_limit_decision()), \
             patch("api.auth_recovery_routes.consume_email_verification_token", return_value=True) as consume:
            result = asyncio.run(verify_email(EmailTokenRequest(token="x" * 32), self.request()))
        self.assertEqual(result["status"], "verified")
        self.assertEqual(calls[0], _limit)
        self.assertIs(calls[1], consume)

    def test_resend_verification_rate_limits_run_in_threadpool(self):
        calls = []
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=False), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=self.threadpool_runner(calls)), \
             patch("api.auth_recovery_routes.consume_rate_limit", return_value=self.rate_limit_decision()):
            result = asyncio.run(resend_verification(EmailAddressRequest(email="user@example.com"), self.request()))
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(calls, [_limit, _limit])

    def test_forgot_password_rate_limits_run_in_threadpool(self):
        calls = []
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=False), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=self.threadpool_runner(calls)), \
             patch("api.auth_recovery_routes.consume_rate_limit", return_value=self.rate_limit_decision()):
            result = asyncio.run(forgot_password(EmailAddressRequest(email="user@example.com"), self.request()))
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(calls, [_limit, _limit])

    def test_password_reset_moves_rate_limit_and_token_consumption_to_threadpool(self):
        calls = []
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=self.threadpool_runner(calls)), \
             patch("api.auth_recovery_routes.consume_rate_limit", return_value=self.rate_limit_decision()), \
             patch("api.auth_recovery_routes.consume_password_reset_token", return_value=True) as consume:
            result = asyncio.run(reset_password(
                PasswordResetRequest(token="x" * 32, new_password="StrongPassword123!"),
                self.request(),
            ))
        self.assertEqual(result["status"], "password_changed")
        self.assertEqual(calls[0], _limit)
        self.assertIs(calls[1], consume)


    def test_resend_email_delivery_helper_runs_in_threadpool_when_configured(self):
        calls = []
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=True), \
             patch("api.auth_recovery_routes.settings.oauth_public_base_url", "https://axion.example"), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=self.threadpool_runner(calls)), \
             patch("api.auth_recovery_routes.consume_rate_limit", return_value=self.rate_limit_decision()), \
             patch("api.auth_recovery_routes._resend_verification_if_pending") as delivery:
            result = asyncio.run(resend_verification(EmailAddressRequest(email="user@example.com"), self.request()))
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(calls[:2], [_limit, _limit])
        self.assertIs(calls[2], delivery)

    def test_password_reset_email_delivery_helper_runs_in_threadpool_when_configured(self):
        calls = []
        with patch("api.auth_recovery_routes.settings.auth_enabled", True), \
             patch("api.auth_recovery_routes.email_delivery_configured", return_value=True), \
             patch("api.auth_recovery_routes.settings.oauth_public_base_url", "https://axion.example"), \
             patch("api.auth_recovery_routes.run_in_threadpool", side_effect=self.threadpool_runner(calls)), \
             patch("api.auth_recovery_routes.consume_rate_limit", return_value=self.rate_limit_decision()), \
             patch("api.auth_recovery_routes._send_password_reset_if_active") as delivery:
            result = asyncio.run(forgot_password(EmailAddressRequest(email="user@example.com"), self.request()))
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(calls[:2], [_limit, _limit])
        self.assertIs(calls[2], delivery)


if __name__ == "__main__":
    unittest.main()
