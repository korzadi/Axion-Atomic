import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from api.ollama import chat_with_usage_stream, parse_chat_response


class _FakeStreamResponse:
    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class _FakeClient:
    def __init__(self, *a, **k):
        self._resp = None

    def set_response(self, resp):
        self._resp = resp

    def stream(self, *a, **k):
        return self._resp

    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class OllamaStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_yields_deltas_and_done_result(self):
        lines = [
            '{"model":"atomic-code:1.1","message":{"content":"Hola"},"done":false}',
            '{"model":"atomic-code:1.1","message":{"content":" mundo"},"done":false}',
            '{"model":"atomic-code:1.1","message":{"content":""},"done":true,"prompt_eval_count":5,"eval_count":2}',
        ]
        fake = _FakeClient()
        fake.set_response(_FakeStreamResponse(lines))
        with patch("api.ollama.httpx.AsyncClient", return_value=fake), \
             patch("api.ollama.settings.chat_model", "atomic-code:1.1"), \
             patch("api.ollama.settings.ollama_base_url", "http://ollama:11434"), \
             patch("api.ollama.settings.ollama_request_timeout_seconds", 30), \
             patch("api.ollama.settings.num_ctx", 4096):
            events = [e async for e in chat_with_usage_stream([{"role": "user", "content": "hi"}])]
        self.assertEqual([e["type"] for e in events], ["delta", "delta", "done"])
        self.assertEqual(events[0]["content"], "Hola")
        self.assertEqual(events[1]["content"], " mundo")
        self.assertEqual(events[2]["result"].content, "Hola mundo")
        self.assertEqual(events[2]["result"].prompt_eval_count, 5)
        self.assertEqual(events[2]["result"].eval_count, 2)

    async def test_stream_raises_without_done(self):
        lines = ['{"model":"m","message":{"content":"x"},"done":false}']
        fake = _FakeClient()
        fake.set_response(_FakeStreamResponse(lines))
        with patch("api.ollama.httpx.AsyncClient", return_value=fake), \
             patch("api.ollama.settings.chat_model", "atomic-code:1.1"), \
             patch("api.ollama.settings.ollama_base_url", "http://ollama:11434"), \
             patch("api.ollama.settings.ollama_request_timeout_seconds", 30), \
             patch("api.ollama.settings.num_ctx", 4096):
            with self.assertRaises(ValueError):
                _ = [e async for e in chat_with_usage_stream([{"role": "user", "content": "hi"}])]


if __name__ == "__main__":
    unittest.main()
