import uuid
import pytest

from api.billing_request_identity import (
    InvalidIdempotencyKey, stable_request_id,
)


def test_request_id_is_stable_for_same_user_and_key():
    first = stable_request_id(user_id="user-1", idempotency_key="req-123")
    second = stable_request_id(user_id="user-1", idempotency_key="req-123")
    assert first == second
    assert str(uuid.UUID(first)) == first


def test_request_id_is_scoped_to_user_and_key():
    base = stable_request_id(user_id="user-1", idempotency_key="req-123")
    assert base != stable_request_id(user_id="user-2", idempotency_key="req-123")
    assert base != stable_request_id(user_id="user-1", idempotency_key="req-456")


@pytest.mark.parametrize("key", ["", "x" * 201, "with space", "bad\nkey", "ñ"])
def test_idempotency_key_rejects_invalid_values(key):
    with pytest.raises(InvalidIdempotencyKey):
        stable_request_id(user_id="user-1", idempotency_key=key)


def test_user_id_is_required():
    with pytest.raises(ValueError):
        stable_request_id(user_id="", idempotency_key="req-1")
