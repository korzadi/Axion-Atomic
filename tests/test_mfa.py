import unittest

from api.mfa import (
    AesGcmTotpCipher,
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
        self.assertNotEqual(hash_recovery_code(codes[0]), codes[0])
        self.assertEqual(hash_recovery_code(codes[0]), hash_recovery_code(codes[0].lower()))

    def test_recovery_code_validation(self):
        with self.assertRaises(ValueError):
            hash_recovery_code("not-a-recovery-code")


if __name__ == "__main__":
    unittest.main()
