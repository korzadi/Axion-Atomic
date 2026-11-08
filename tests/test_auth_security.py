import unittest
from unittest.mock import patch

from api.auth import hash_password, verify_password, _digest


class PasswordSecurityTests(unittest.TestCase):
    def test_password_hash_is_not_plaintext_and_verifies(self):
        password = "correct horse battery staple 2026"
        hashed = hash_password(password)
        self.assertNotEqual(hashed, password)
        self.assertTrue(verify_password(hashed, password))
        self.assertFalse(verify_password(hashed, "wrong password"))

    def test_password_policy_rejects_short_values(self):
        with self.assertRaises(ValueError):
            hash_password("short")

    def test_session_token_digest_is_deterministic(self):
        self.assertEqual(_digest("opaque-token"), _digest("opaque-token"))
        self.assertNotEqual(_digest("opaque-token"), _digest("different-token"))


    def test_inactive_account_still_verifies_password_before_rejection(self):
        from unittest.mock import Mock, patch
        from fastapi import HTTPException
        from api.auth import verify_credentials

        row = {
            "id": "inactive-user",
            "email": "inactive@example.com",
            "display_name": "Inactive",
            "password_hash": "argon-hash",
            "status": "disabled",
        }
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        result = Mock()
        result.mappings.return_value.first.return_value = row
        connection.execute.return_value = result

        with patch("api.auth.engine.connect", return_value=connection):
            with patch("api.auth.verify_password", return_value=True) as verify:
                with self.assertRaises(HTTPException) as raised:
                    verify_credentials("inactive@example.com", "StrongPassword123!")
        self.assertEqual(raised.exception.status_code, 401)
        verify.assert_called_once_with("argon-hash", "StrongPassword123!")


if __name__ == "__main__":
    unittest.main()
