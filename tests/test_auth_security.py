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


if __name__ == "__main__":
    unittest.main()
