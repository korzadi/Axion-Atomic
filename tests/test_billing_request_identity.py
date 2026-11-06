import uuid
import pytest

from api.billing_request_identity import (
    InvalidIdempotencyKey, stable_request_id, request_payload_sha256,
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



def _fingerprint(**overrides):
    payload = {
        "project_id": "project-a",
        "model": "atomic-code",
        "messages": [{"role": "user", "content": "hola"}],
        "temperature": 0.2,
        "max_tokens": 1024,
        "policy_version": "atomic-code-budget-v1",
    }
    payload.update(overrides)
    return request_payload_sha256(**payload)


def test_payload_fingerprint_is_stable_and_order_independent_for_object_keys():
    first = _fingerprint()
    second = _fingerprint(messages=[{"content": "hola", "role": "user"}])
    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize("change", [
    {"project_id": "project-b"},
    {"model": "other-model"},
    {"messages": [{"role": "user", "content": "different"}]},
    {"temperature": 0.7},
    {"max_tokens": 2048},
    {"policy_version": "new-policy"},
])
def test_payload_fingerprint_changes_when_execution_inputs_change(change):
    assert _fingerprint() != _fingerprint(**change)


def test_payload_fingerprint_rejects_non_finite_generation_values():
    with pytest.raises(ValueError):
        _fingerprint(temperature=float("nan"))
