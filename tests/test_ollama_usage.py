import asyncio
import httpx
import pytest
from unittest.mock import AsyncMock

from api.ollama import chat, chat_with_usage, parse_chat_response


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


def test_chat_with_usage_sends_non_streaming_request_and_parses_response(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "atomic-code:actual",
                "message": {"role": "assistant", "content": "respuesta"},
                "done": True,
                "prompt_eval_count": 9,
                "eval_count": 4,
                "total_duration": 100,
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, json):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr("api.ollama.httpx.AsyncClient", FakeAsyncClient)
    result = asyncio.run(chat_with_usage(
        [{"role": "user", "content": "hola"}],
        temperature=0.3,
        max_tokens=64,
    ))

    assert result.content == "respuesta"
    assert result.prompt_eval_count == 9
    assert result.eval_count == 4
    assert result.returned_model == "atomic-code:actual"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hola"}]
    assert captured["payload"]["options"]["temperature"] == 0.3
    assert captured["payload"]["options"]["num_predict"] == 64
    assert captured["url"].endswith("/api/chat")


def test_chat_with_usage_propagates_transport_timeout(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, json):
            raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr("api.ollama.httpx.AsyncClient", FakeAsyncClient)
    with pytest.raises(httpx.TimeoutException):
        asyncio.run(chat_with_usage([{"role": "user", "content": "hola"}]))


def test_legacy_chat_wrapper_still_returns_only_text(monkeypatch):
    mocked = AsyncMock(return_value=type("Result", (), {
        "content": "solo texto",
        "requested_model": "atomic-code:1.1",
        "returned_model": "atomic-code:1.1",
        "done": True,
    })())
    monkeypatch.setattr("api.ollama.chat_with_usage", mocked)

    result = asyncio.run(chat([{"role": "user", "content": "hola"}]))

    assert result == "solo texto"
    mocked.assert_awaited_once()
