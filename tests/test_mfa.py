import os
import unittest
from unittest.mock import patch

from api.mfa import (
    AesGcmTotpCipher,
    EnvironmentMfaKeyProvider,
    MfaError,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    matching_totp_counter,
    totp_at,
)


class StaticKeyProvider:
    def __init__(self):
        self.key = b"k" * 32

    def active_key(self):
        return "test-key-v1", self.key

    def get_key(self, key_id):
        if key_id != "test-key-v1":
            raise KeyError(key_id)
        return self.key


class TotpPrimitiveTests(unittest.TestCase):
    SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_environment_key_provider_requires_valid_runtime_secret(self):
        provider = EnvironmentMfaKeyProvider()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MfaError):
                provider.active_key()
        with patch.dict(os.environ, {
            "AXION_MFA_ENCRYPTION_KEY_ID": "runtime-v1",
            "AXION_MFA_ENCRYPTION_KEY_B64": "not-base64!",
        }, clear=True):
            with self.assertRaises(MfaError):
                provider.active_key()
        import base64
        encoded = base64.b64encode(b"r" * 32).decode("ascii")
        with patch.dict(os.environ, {
            "AXION_MFA_ENCRYPTION_KEY_ID": "runtime-v1",
            "AXION_MFA_ENCRYPTION_KEY_B64": encoded,
        }, clear=True):
            self.assertEqual(provider.active_key(), ("runtime-v1", b"r" * 32))
            self.assertEqual(provider.get_key("runtime-v1"), b"r" * 32)
            with self.assertRaises(MfaError):
                provider.get_key("old-key")

        historical = base64.b64encode(b"h" * 32).decode("ascii")
        with patch.dict(os.environ, {
            "AXION_MFA_ENCRYPTION_KEY_ID": "runtime-v2",
            "AXION_MFA_ENCRYPTION_KEY_B64": encoded,
            "AXION_MFA_ENCRYPTION_KEYRING_B64": (
                '{"runtime-v1":"' + historical + '"}'
            ),
        }, clear=True):
            self.assertEqual(provider.get_key("runtime-v1"), b"h" * 32)
            with self.assertRaises(MfaError):
                provider.get_key("unknown-key")

    def test_cipher_decrypts_with_historical_keyring_after_rotation(self):
        import base64
        old_provider = StaticKeyProvider()
        cipher_before_rotation = AesGcmTotpCipher(old_provider)
        encrypted = cipher_before_rotation.encrypt(self.SECRET, user_id="user-rotation")
        old_key = base64.b64encode(old_provider.key).decode("ascii")
        active_key = base64.b64encode(b"n" * 32).decode("ascii")
        with patch.dict(os.environ, {
            "AXION_MFA_ENCRYPTION_KEY_ID": "new-key-v2",
            "AXION_MFA_ENCRYPTION_KEY_B64": active_key,
            "AXION_MFA_ENCRYPTION_KEYRING_B64": '{"test-key-v1":"' + old_key + '"}',
        }, clear=True):
            rotated_cipher = AesGcmTotpCipher(EnvironmentMfaKeyProvider())
            self.assertEqual(
                rotated_cipher.decrypt(encrypted, user_id="user-rotation"),
                self.SECRET,
            )

    def test_rfc6238_sha1_vector(self):
        self.assertEqual(totp_at(self.SECRET, 59, digits=8), "94287082")

    def test_matching_counter_accepts_once_and_rejects_replay(self):
        code = totp_at(self.SECRET, 59)
        counter = matching_totp_counter(self.SECRET, code, now=59, window=0)
        self.assertEqual(counter, 1)
        self.assertIsNone(matching_totp_counter(
            self.SECRET, code, now=59, window=0, last_accepted_counter=counter
        ))

    def test_matching_counter_rejects_malformed_code(self):
        self.assertIsNone(matching_totp_counter(self.SECRET, "12x456", now=59))

    def test_generated_secret_is_valid_and_random(self):
        first = generate_totp_secret()
        second = generate_totp_secret()
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 32)
        self.assertTrue(totp_at(first, 1).isdigit())

    def test_encrypted_secret_round_trip_and_user_binding(self):
        cipher = AesGcmTotpCipher(StaticKeyProvider())
        encrypted = cipher.encrypt(self.SECRET, user_id="user-1")
        self.assertEqual(cipher.decrypt(encrypted, user_id="user-1"), self.SECRET)
        with self.assertRaises(MfaError):
            cipher.decrypt(encrypted, user_id="user-2")

    def test_recovery_codes_are_unique_and_only_hashes_are_stored(self):
        codes = generate_recovery_codes()
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        self.assertTrue(all(len(code) == 32 for code in codes))
        self.assertNotEqual(hash_recovery_code(codes[0]), codes[0])
        self.assertEqual(hash_recovery_code(codes[0]), hash_recovery_code(codes[0].lower()))

    def test_recovery_code_validation(self):
        with self.assertRaises(ValueError):
            hash_recovery_code("not-a-recovery-code")


if __name__ == "__main__":
    unittest.main()
