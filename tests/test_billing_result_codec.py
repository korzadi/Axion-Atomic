import pytest
from api.ollama import InferenceResult
from api.billing_result_codec import (
    InferenceResultCodecError, serialize_inference_result,
    deserialize_inference_result,
)


def sample():
    return InferenceResult(
        content="Respuesta protegida ñ",
        requested_model="atomic-code:16k-8k",
        returned_model="atomic-code:16k-8k",
        done=True, prompt_eval_count=12, eval_count=8,
        total_duration_ns=100, load_duration_ns=10,
        prompt_eval_duration_ns=20, eval_duration_ns=30,
        usage_source="ollama_response",
    )


def test_result_codec_round_trip_is_deterministic():
    result = sample()
    first = serialize_inference_result(result)
    assert first == serialize_inference_result(result)
    assert deserialize_inference_result(first) == result


def test_result_codec_rejects_unknown_or_missing_fields():
    with pytest.raises(InferenceResultCodecError):
        deserialize_inference_result(b'{"content":"x"}')


def test_result_codec_rejects_boolean_token_counter():
    result = sample()
    invalid = InferenceResult(
        **{**result.__dict__, "prompt_eval_count": True}
    )
    with pytest.raises(InferenceResultCodecError):
        serialize_inference_result(invalid)


def test_result_codec_rejects_oversized_payload():
    with pytest.raises(InferenceResultCodecError):
        deserialize_inference_result(b"x" * (2 * 1024 * 1024 + 1))
