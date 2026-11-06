"""Pruebas puras del envelope cifrable de ejecución y medición."""
import json

import pytest

from api.billing_execution_envelope import (
    ExecutionEnvelopeError,
    build_execution_envelope,
    parse_execution_envelope,
)
from api.billing_policy import UsageUnavailable
from api.ollama import InferenceResult


def _result(**overrides):
    values = {
        "content": "respuesta privada",
        "requested_model": "atomic-code:16k-8k",
        "returned_model": "atomic-code:16k-8k",
        "done": True,
        "prompt_eval_count": 100,
        "eval_count": 25,
        "total_duration_ns": 1000,
        "load_duration_ns": 10,
        "prompt_eval_duration_ns": 500,
        "eval_duration_ns": 400,
        "usage_source": "ollama_response",
    }
    values.update(overrides)
    return InferenceResult(**values)


def _build(result=None):
    return build_execution_envelope(
        result or _result(),
        expected_model="atomic-code:16k-8k",
        policy_version="atomic-code-v1",
        input_weight=2,
        output_weight=3,
    )


def test_envelope_contains_result_and_metering_in_one_versioned_payload():
    parsed = parse_execution_envelope(_build())
    assert parsed.content == "respuesta privada"
    assert parsed.prompt_tokens == 100
    assert parsed.output_tokens == 25
    assert parsed.credits == 275
    assert parsed.policy_version == "atomic-code-v1"


def test_envelope_serialization_is_deterministic():
    assert _build() == _build()


@pytest.mark.parametrize(
    "overrides",
    [
        {"requested_model": "other"},
        {"returned_model": "other"},
        {"done": False},
        {"usage_source": "unavailable"},
        {"prompt_eval_count": None},
        {"eval_count": None},
    ],
)
def test_unverifiable_inference_cannot_build_envelope(overrides):
    if overrides.get("usage_source") == "unavailable" or overrides.get("prompt_eval_count") is None or overrides.get("eval_count") is None:
        with pytest.raises((UsageUnavailable, ExecutionEnvelopeError)):
            _build(_result(**overrides))
    else:
        with pytest.raises(ExecutionEnvelopeError):
            _build(_result(**overrides))


def test_parser_rejects_credit_tampering():
    payload = json.loads(_build())
    payload["credits"] += 1
    with pytest.raises(ExecutionEnvelopeError):
        parse_execution_envelope(json.dumps(payload).encode())


def test_parser_rejects_unknown_or_missing_fields():
    payload = json.loads(_build())
    payload["untrusted_extra"] = True
    with pytest.raises(ExecutionEnvelopeError):
        parse_execution_envelope(json.dumps(payload).encode())


def test_parser_rejects_invalid_json_and_empty_bytes():
    with pytest.raises(ExecutionEnvelopeError):
        parse_execution_envelope(b"")
    with pytest.raises(ExecutionEnvelopeError):
        parse_execution_envelope(b"not-json")


def test_boolean_counters_are_rejected():
    payload = json.loads(_build())
    payload["prompt_tokens"] = True
    with pytest.raises(ExecutionEnvelopeError):
        parse_execution_envelope(json.dumps(payload).encode())
