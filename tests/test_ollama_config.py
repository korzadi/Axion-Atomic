import unittest
from unittest.mock import AsyncMock, patch

from api import ollama


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    last_request = None

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        FakeAsyncClient.last_request = {"url": url, "json": json, "timeout": self.timeout}
        if url.endswith("/api/chat"):
            return FakeResponse({"model": json["model"], "done": True, "message": {"content": "ok"}})
        return FakeResponse({"embedding": [0.1, 0.2]})


class FakeTagsClient:
    payload = {"models": [{"name": "atomic-code:1.1"}, {"name": "nomic-embed-text:latest"}]}

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        self.last_url = url
        return FakeResponse(self.payload)


class OllamaClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_uses_configured_model_and_context(self):
        with patch.object(ollama, "settings") as settings, patch.object(
            ollama.httpx, "AsyncClient", FakeAsyncClient
        ):
            settings.chat_model = "atomic-code:1.1"
            settings.num_ctx = 16384
            settings.ollama_base_url = "http://ollama:11434"
            result = await ollama.chat([{"role": "user", "content": "hola"}], max_tokens=512)

        self.assertEqual(result, "ok")
        request = FakeAsyncClient.last_request
        self.assertEqual(request["url"], "http://ollama:11434/api/chat")
        self.assertEqual(request["json"]["model"], "atomic-code:1.1")
        self.assertEqual(request["json"]["options"]["num_ctx"], 16384)
        self.assertEqual(request["json"]["options"]["num_predict"], 512)

    async def test_chat_rejects_unexpected_model_identity(self):
        from api.ollama import InferenceResult
        invalid = InferenceResult(
            content="respuesta", requested_model="atomic-code:1.1", returned_model="other-model",
            done=True, prompt_eval_count=1, eval_count=1, total_duration_ns=1,
            load_duration_ns=None, prompt_eval_duration_ns=None, eval_duration_ns=None,
            usage_source="ollama_response",
        )
        with patch.object(ollama, "settings") as settings, patch.object(
            ollama, "chat_with_usage", new=AsyncMock(return_value=invalid)
        ):
            settings.chat_model = "atomic-code:1.1"
            with self.assertRaisesRegex(RuntimeError, "no coincide"):
                await ollama.chat([{"role": "user", "content": "hola"}])

    async def test_chat_rejects_incomplete_inference(self):
        from api.ollama import InferenceResult
        invalid = InferenceResult(
            content="respuesta", requested_model="atomic-code:1.1", returned_model="atomic-code:1.1",
            done=False, prompt_eval_count=1, eval_count=1, total_duration_ns=1,
            load_duration_ns=None, prompt_eval_duration_ns=None, eval_duration_ns=None,
            usage_source="ollama_response",
        )
        with patch.object(ollama, "settings") as settings, patch.object(
            ollama, "chat_with_usage", new=AsyncMock(return_value=invalid)
        ):
            settings.chat_model = "atomic-code:1.1"
            with self.assertRaisesRegex(RuntimeError, "no terminó"):
                await ollama.chat([{"role": "user", "content": "hola"}])

    async def test_model_availability_requires_exact_configured_ollama_tag(self):
        with patch.object(ollama, "settings") as settings, patch.object(
            ollama.httpx, "AsyncClient", FakeTagsClient
        ):
            settings.chat_model = "atomic-code:1.1"
            settings.ollama_base_url = "http://ollama:11434"
            settings.ollama_request_timeout_seconds = 30
            self.assertTrue(await ollama.configured_chat_model_available())

    async def test_model_availability_is_false_when_configured_tag_is_missing(self):
        with patch.object(ollama, "settings") as settings, patch.object(
            ollama.httpx, "AsyncClient", FakeTagsClient
        ):
            settings.chat_model = "atomic-code:missing"
            settings.ollama_base_url = "http://ollama:11434"
            settings.ollama_request_timeout_seconds = 30
            self.assertFalse(await ollama.configured_chat_model_available())

    async def test_embeddings_use_configured_embedding_model(self):
        with patch.object(ollama, "settings") as settings, patch.object(
            ollama.httpx, "AsyncClient", FakeAsyncClient
        ):
            settings.embed_model = "nomic-embed-text"
            settings.embed_dimension = 2
            settings.ollama_request_timeout_seconds = 120
            settings.ollama_base_url = "http://ollama:11434"
            result = await ollama.embed("texto de prueba")

        self.assertEqual(result, [0.1, 0.2])
        request = FakeAsyncClient.last_request
        self.assertEqual(request["url"], "http://ollama:11434/api/embeddings")
        self.assertEqual(request["json"]["model"], "nomic-embed-text")


if __name__ == "__main__":
    unittest.main()
