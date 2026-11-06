import pytest

from api.ollama import parse_chat_response


def test_parse_complete_ollama_usage():
    result = parse_chat_response(
        {
            "model": "atomic-code:16k-8k",
            "message": {"role": "assistant", "content": "hola"},
            "done": True,
            "prompt_eval_count": 12,
            "eval_count": 7,
            "total_duration": 100,
            "load_duration": 20,
            "prompt_eval_duration": 30,
            "eval_duration": 40,
        },
        requested_model="atomic-code:16k-8k",
    )
    assert result.content == "hola"
    assert result.prompt_eval_count == 12
    assert result.eval_count == 7
    assert result.usage_source == "ollama_response"
    assert result.total_duration_ns == 100


def test_missing_counters_are_unknown_not_zero():
    result = parse_chat_response(
        {"message": {"content": "hola"}, "prompt_eval_count": 0},
        requested_model="atomic-code:16k-8k",
    )
    assert result.prompt_eval_count == 0
    assert result.eval_count is None
    assert result.usage_source == "unavailable"


@pytest.mark.parametrize("invalid", [-1, 1.5, "4", True, None])
def test_invalid_counter_is_not_accepted_as_usage(invalid):
    result = parse_chat_response(
        {
            "message": {"content": "hola"},
            "prompt_eval_count": invalid,
            "eval_count": 2,
        },
        requested_model="atomic-code:16k-8k",
    )
    assert result.prompt_eval_count is None
    assert result.eval_count == 2
    assert result.usage_source == "unavailable"


def test_invalid_message_content_is_rejected():
    with pytest.raises(ValueError):
        parse_chat_response({"message": {"content": None}}, "atomic-code:16k-8k")


def test_requested_and_returned_models_are_kept_separate():
    result = parse_chat_response(
        {
            "model": "different-model:latest",
            "message": {"content": "ok"},
        },
        requested_model="configured-model",
    )
    assert result.requested_model == "configured-model"
    assert result.returned_model == "different-model:latest"
