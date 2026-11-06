import unittest
from unittest.mock import patch

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
            return FakeResponse({"message": {"content": "ok"}})
        return FakeResponse({"embedding": [0.1, 0.2]})


class OllamaClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_uses_configured_model_and_context(self):
        with patch.object(ollama, "settings") as settings, patch.object(
            ollama.httpx, "AsyncClient", FakeAsyncClient
        ):
            settings.chat_model = "atomic-code:16k-8k"
            settings.num_ctx = 16384
            settings.ollama_base_url = "http://ollama:11434"
            result = await ollama.chat([{"role": "user", "content": "hola"}], max_tokens=512)

        self.assertEqual(result, "ok")
        request = FakeAsyncClient.last_request
        self.assertEqual(request["url"], "http://ollama:11434/api/chat")
        self.assertEqual(request["json"]["model"], "atomic-code:16k-8k")
        self.assertEqual(request["json"]["options"]["num_ctx"], 16384)
        self.assertEqual(request["json"]["options"]["num_predict"], 512)

    async def test_embeddings_use_configured_embedding_model(self):
        with patch.object(ollama, "settings") as settings, patch.object(
            ollama.httpx, "AsyncClient", FakeAsyncClient
        ):
            settings.embed_model = "nomic-embed-text"
            settings.ollama_base_url = "http://ollama:11434"
            result = await ollama.embed("texto de prueba")

        self.assertEqual(result, [0.1, 0.2])
        request = FakeAsyncClient.last_request
        self.assertEqual(request["url"], "http://ollama:11434/api/embeddings")
        self.assertEqual(request["json"]["model"], "nomic-embed-text")


if __name__ == "__main__":
    unittest.main()
