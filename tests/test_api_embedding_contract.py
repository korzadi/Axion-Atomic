import unittest
from unittest.mock import AsyncMock, patch

import api.ollama as ollama


class FakeResponse:
    def __init__(self, vector):
        self.vector = vector

    def raise_for_status(self):
        return None

    def json(self):
        return {"embedding": self.vector}


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.response = FakeResponse([0.1, float("nan")])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return self.response


class ApiEmbeddingContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_remote_vector_is_not_cached(self):
        with (
            patch.object(ollama.settings, "embed_dimension", 2),
            patch.object(ollama, "get_embedding", new=AsyncMock(return_value=None)),
            patch.object(ollama, "set_embedding", new=AsyncMock()) as cache_write,
            patch.object(ollama.httpx, "AsyncClient", FakeAsyncClient),
        ):
            with self.assertRaisesRegex(ValueError, "no finito"):
                await ollama.embed("texto")
            cache_write.assert_not_awaited()

    async def test_invalid_cached_vector_is_rejected(self):
        with (
            patch.object(ollama.settings, "embed_dimension", 2),
            patch.object(ollama, "get_embedding", new=AsyncMock(return_value=[0.1, float("inf")])),
            patch.object(ollama, "set_embedding", new=AsyncMock()) as cache_write,
            patch.object(ollama.httpx, "AsyncClient", FakeAsyncClient) as http_client,
        ):
            with self.assertRaisesRegex(ValueError, "no finito"):
                await ollama.embed("texto")
            cache_write.assert_not_awaited()
            http_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
