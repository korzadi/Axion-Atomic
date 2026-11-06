"""Tests puros para medición de uso facturable; no acceden a PostgreSQL."""
import pytest

from api.billing_metering import ModelRatePolicy, calculate_inference_charge
from api.billing_policy import UsageUnavailable
from api.ollama import InferenceResult


def _result(**overrides):
    values = {
        "content": "respuesta",
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


def _policy(**overrides):
    values = {
        "model_name": "atomic-code:16k-8k",
        "version": "atomic-code-v1",
        "input_weight": 1,
        "output_weight": 1,
        "enabled": True,
    }
    values.update(overrides)
    return ModelRatePolicy(**values)


def test_calculates_credits_and_preserves_rate_snapshot():
    charge = calculate_inference_charge(_result(), _policy())
    assert charge.credits == 125
    assert charge.prompt_tokens == 100
    assert charge.output_tokens == 25
    assert charge.policy_version == "atomic-code-v1"


def test_uses_independent_input_and_output_weights():
    charge = calculate_inference_charge(
        _result(), _policy(input_weight=2, output_weight=3)
    )
    assert charge.credits == 275


def test_disabled_model_cannot_be_charged():
    with pytest.raises(PermissionError):
        calculate_inference_charge(_result(), _policy(enabled=False))


@pytest.mark.parametrize("done", [False, None])
def test_non_final_inference_cannot_be_charged(done):
    with pytest.raises(UsageUnavailable):
        calculate_inference_charge(_result(done=done), _policy())


@pytest.mark.parametrize(
    "overrides",
    [
        {"prompt_eval_count": None},
        {"eval_count": None},
        {"usage_source": "unavailable"},
    ],
)
def test_missing_or_untrusted_usage_cannot_be_charged(overrides):
    with pytest.raises(UsageUnavailable):
        calculate_inference_charge(_result(**overrides), _policy())


def test_model_must_match_explicit_rate_policy():
    with pytest.raises(ValueError):
        calculate_inference_charge(_result(), _policy(model_name="other-model"))


def test_boolean_token_counter_is_rejected():
    with pytest.raises(ValueError):
        calculate_inference_charge(_result(prompt_eval_count=True), _policy())


def test_zero_token_result_is_valid_but_does_not_invent_usage():
    charge = calculate_inference_charge(
        _result(prompt_eval_count=0, eval_count=0), _policy()
    )
    assert charge.credits == 0



def test_model_enablement_requires_literal_true():
    with pytest.raises(PermissionError):
        calculate_inference_charge(_result(), _policy(enabled="true"))
