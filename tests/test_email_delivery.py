import unittest
from unittest.mock import Mock, patch

from api.email_delivery import email_delivery_configured, send_transactional_email, send_verification_email, send_password_reset_email
from api.auth_recovery_routes import _gate
from fastapi import HTTPException


class EmailDeliveryTests(unittest.TestCase):
    def test_requires_host_sender_and_tls(self):
        settings = Mock(smtp_host="smtp.example", email_from="no-reply@example",
                        smtp_starttls=False, smtp_ssl=False, smtp_username=None, smtp_password=None,
                        smtp_port=587)
        self.assertFalse(email_delivery_configured(settings))
        settings.smtp_starttls = True
        self.assertTrue(email_delivery_configured(settings))

    def test_rejects_username_without_password(self):
        settings = Mock(smtp_host="smtp.example", email_from="no-reply@example",
                        smtp_starttls=True, smtp_ssl=False,
                        smtp_username="smtp-user", smtp_password=None, smtp_port=587)
        self.assertFalse(email_delivery_configured(settings))

    def test_rejects_password_without_username(self):
        settings = Mock(smtp_host="smtp.example", email_from="no-reply@example",
                        smtp_starttls=True, smtp_ssl=False,
                        smtp_username=None, smtp_password="orphaned-password", smtp_port=587)
        self.assertFalse(email_delivery_configured(settings))

    def test_rejects_invalid_port(self):
        settings = Mock(smtp_host="smtp.example", email_from="no-reply@example",
                        smtp_starttls=True, smtp_ssl=False,
                        smtp_username=None, smtp_password=None, smtp_port=70000)
        self.assertFalse(email_delivery_configured(settings))

    def test_rejects_conflicting_tls_modes(self):
        settings = Mock(smtp_host="smtp.example", email_from="no-reply@example",
                        smtp_starttls=True, smtp_ssl=True,
                        smtp_username=None, smtp_password=None, smtp_port=587)
        self.assertFalse(email_delivery_configured(settings))

    def test_refuses_plaintext_smtp(self):
        settings = Mock(smtp_host="smtp.example", email_from="no-reply@example",
                        smtp_starttls=False, smtp_ssl=False, smtp_username=None,
                        smtp_password=None, smtp_port=587)
        with self.assertRaises(RuntimeError):
            send_transactional_email(settings=settings, recipient="user@example.com",
                                     subject="test", body="test")

    @patch("api.email_delivery.smtplib.SMTP")
    def test_starttls_is_required_before_message_delivery(self, smtp_class):
        server = smtp_class.return_value.__enter__.return_value
        settings = Mock(smtp_host="smtp.example", smtp_port=587, email_from="no-reply@example",
                        smtp_starttls=True, smtp_ssl=False, smtp_username=None, smtp_password=None)
        send_transactional_email(settings=settings, recipient="user@example.com",
                                  subject="test", body="test")
        server.starttls.assert_called_once()
        server.send_message.assert_called_once()

    @patch("api.email_delivery.smtplib.SMTP_SSL")
    def test_implicit_tls_uses_ssl_transport(self, smtp_ssl_class):
        server = smtp_ssl_class.return_value.__enter__.return_value
        settings = Mock(smtp_host="smtp.example", smtp_port=465, email_from="no-reply@example",
                        smtp_starttls=False, smtp_ssl=True, smtp_username=None, smtp_password=None)
        send_transactional_email(settings=settings, recipient="user@example.com",
                                  subject="test", body="test")
        smtp_ssl_class.assert_called_once()
        server.send_message.assert_called_once()

    @patch("api.email_delivery.smtplib.SMTP")
    def test_authentication_occurs_after_starttls(self, smtp_class):
        server = smtp_class.return_value.__enter__.return_value
        settings = Mock(smtp_host="smtp.example", smtp_port=587, email_from="no-reply@example",
                        smtp_starttls=True, smtp_ssl=False, smtp_username="smtp-user",
                        smtp_password="smtp-password")
        send_transactional_email(settings=settings, recipient="user@example.com",
                                  subject="test", body="test")
        self.assertLess(server.starttls.call_count, 2)
        server.login.assert_called_once_with("smtp-user", "smtp-password")
        server.send_message.assert_called_once()

    @patch("api.email_delivery.smtplib.SMTP")
    def test_starttls_failure_prevents_message_delivery(self, smtp_class):
        server = smtp_class.return_value.__enter__.return_value
        server.starttls.side_effect = RuntimeError("TLS negotiation failed")
        settings = Mock(smtp_host="smtp.example", smtp_port=587, email_from="no-reply@example",
                        smtp_starttls=True, smtp_ssl=False, smtp_username=None, smtp_password=None)
        with self.assertRaises(RuntimeError):
            send_transactional_email(settings=settings, recipient="user@example.com",
                                      subject="test", body="test")
        server.send_message.assert_not_called()

    @patch("api.email_delivery.send_transactional_email")
    def test_verification_and_password_reset_emails_use_final_axyron_brand(self, send_email):
        settings = Mock(oauth_public_base_url="https://axyronatomic.com")
        send_verification_email(settings=settings, recipient="user@example.com", token="verification-token")
        verification = send_email.call_args.kwargs
        self.assertIn("AXYRON ATOMIC", verification["subject"])
        self.assertIn("AXYRON ATOMIC", verification["body"])
        send_password_reset_email(settings=settings, recipient="user@example.com", token="reset-token")
        reset = send_email.call_args.kwargs
        self.assertIn("AXYRON ATOMIC", reset["subject"])
        self.assertIn("AXYRON ATOMIC", reset["body"])
        self.assertNotIn("AXION ATOMIC", verification["subject"] + verification["body"] + reset["subject"] + reset["body"])


class RecoveryGateTests(unittest.TestCase):
    def test_recovery_routes_fail_closed_until_auth_is_enabled(self):
        with patch("api.auth_recovery_routes.settings.auth_enabled", False):
            with self.assertRaises(HTTPException) as raised:
                _gate()
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
