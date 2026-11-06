import uuid

import pytest

from api.billing_result_crypto import (
    AesGcmResultCipher,
    EncryptedResult,
    ResultEncryptionError,
)


class FakeKeyProvider:
    def __init__(self):
        self.keys = {"key-v1": b"1" * 32, "key-v2": b"2" * 32}
        self.current = "key-v1"

    def active_key(self):
        return self.current, self.keys[self.current]

    def get_key(self, key_id):
        return self.keys[key_id]


def context():
    return {
        "user_id": str(uuid.uuid4()),
        "reservation_id": str(uuid.uuid4()),
        "execution_id": str(uuid.uuid4()),
    }


def test_aes_gcm_round_trip_and_key_rotation():
    provider = FakeKeyProvider()
    cipher = AesGcmResultCipher(provider)
    ctx = context()
    first = cipher.encrypt(b"private inference result", **ctx)
    assert first.key_id == "key-v1"
    assert cipher.decrypt(first, **ctx) == b"private inference result"

    provider.current = "key-v2"
    second = cipher.encrypt(b"new result", **ctx)
    assert second.key_id == "key-v2"
    assert cipher.decrypt(first, **ctx) == b"private inference result"
    assert cipher.decrypt(second, **ctx) == b"new result"


def test_ciphertext_cannot_be_moved_to_another_context():
    cipher = AesGcmResultCipher(FakeKeyProvider())
    ctx = context()
    encrypted = cipher.encrypt(b"result", **ctx)
    other = {**ctx, "user_id": str(uuid.uuid4())}
    with pytest.raises(ResultEncryptionError):
        cipher.decrypt(encrypted, **other)


def test_tampered_ciphertext_is_rejected():
    cipher = AesGcmResultCipher(FakeKeyProvider())
    ctx = context()
    encrypted = cipher.encrypt(b"result", **ctx)
    tampered = EncryptedResult(
        ciphertext=encrypted.ciphertext[:-1] + bytes([encrypted.ciphertext[-1] ^ 1]),
        nonce=encrypted.nonce,
        key_id=encrypted.key_id,
    )
    with pytest.raises(ResultEncryptionError):
        cipher.decrypt(tampered, **ctx)


def test_wrong_or_missing_key_is_not_silently_accepted():
    provider = FakeKeyProvider()
    cipher = AesGcmResultCipher(provider)
    ctx = context()
    encrypted = cipher.encrypt(b"result", **ctx)
    provider.keys["key-v1"] = b"x" * 32
    with pytest.raises(ResultEncryptionError):
        cipher.decrypt(encrypted, **ctx)


def test_invalid_key_length_is_rejected():
    class BadProvider:
        def active_key(self):
            return "bad-key", b"short"

        def get_key(self, key_id):
            return b"short"

    with pytest.raises(ResultEncryptionError):
        AesGcmResultCipher(BadProvider()).encrypt(b"result", **context())
