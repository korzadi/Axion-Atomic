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


def _attested_fingerprint(**overrides):
    from api.billing_request_identity import attested_request_payload_sha256

    payload = {
        "project_id": "project-a",
        "public_model": "atomic-code",
        "runtime_model": "atomic-code:16k-8k",
        "model_digest": "sha256:model-digest",
        "template_sha256": "sha256:template-digest",
        "tokenizer_id": "qwen2-byte-fallback:v1",
        "effective_messages": [
            {"role": "system", "content": "server policy"},
            {"role": "user", "content": "hola"},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
        "policy_version": "atomic-code-budget-v1",
    }
    payload.update(overrides)
    return attested_request_payload_sha256(**payload)


def test_attested_fingerprint_changes_when_server_context_changes():
    first = _attested_fingerprint()
    changed = _attested_fingerprint(effective_messages=[
        {"role": "system", "content": "changed RAG context"},
        {"role": "user", "content": "hola"},
    ])
    assert first != changed


@pytest.mark.parametrize("field", [
    "runtime_model", "model_digest", "template_sha256", "tokenizer_id",
])
def test_attested_fingerprint_requires_runtime_identity(field):
    with pytest.raises(ValueError):
        _attested_fingerprint(**{field: ""})


def test_attested_fingerprint_changes_when_runtime_attestation_changes():
    assert _attested_fingerprint() != _attested_fingerprint(
        model_digest="sha256:another-model-digest"
    )

 
@pytest.mark.parametrize("temperature", [-0.01, 2.01, True, float("inf"), float("-inf")])
def test_payload_fingerprint_rejects_temperature_outside_api_contract(temperature):
    with pytest.raises(ValueError):
        _fingerprint(temperature=temperature)
