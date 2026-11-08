import unittest
from unittest.mock import patch

from core.errors import TransportError
from core.ollama_transport import OllamaTransport
from rag.embedding_identity import (
    EmbeddingIdentity,
    canonical_model_name,
    require_compatible_embeddings,
    same_model,
)


class EmbeddingIdentityTests(unittest.TestCase):
    def test_implicit_latest_alias_is_canonicalized(self):
        self.assertEqual(canonical_model_name(" nomic-embed-text "), "nomic-embed-text:latest")
        self.assertTrue(same_model("nomic-embed-text", "nomic-embed-text:latest"))

    def test_different_model_tags_are_not_equivalent(self):
        self.assertFalse(same_model("nomic-embed-text:v1", "nomic-embed-text:v2"))
        self.assertFalse(same_model("nomic-embed-text", "mxbai-embed-large"))

    def test_rejects_empty_or_spaced_model_names(self):
        for model in ("", "  ", "nomic embed"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                EmbeddingIdentity(model, 768)

    def test_rejects_invalid_dimensions(self):
        for dimension in (0, -1, True, 768.0):
            with self.subTest(dimension=dimension), self.assertRaises(ValueError):
                EmbeddingIdentity("nomic-embed-text", dimension)

    def test_compatibility_requires_same_canonical_model_and_dimension(self):
        expected = EmbeddingIdentity("nomic-embed-text", 768)
        require_compatible_embeddings(expected, EmbeddingIdentity("nomic-embed-text:latest", 768))
        with self.assertRaisesRegex(ValueError, "incompatible"):
            require_compatible_embeddings(expected, EmbeddingIdentity("nomic-embed-text:v2", 768))
        with self.assertRaisesRegex(ValueError, "incompatible"):
            require_compatible_embeddings(expected, EmbeddingIdentity("nomic-embed-text", 1024))


class OllamaTransportIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_runtime_model_mismatch(self):
        transport = OllamaTransport("http://ollama:11434")
        with patch.object(transport, "_post_json", return_value={
            "model": "other-model:latest", "embeddings": [[0.1, 0.2]],
        }):
            with self.assertRaisesRegex(TransportError, "modelo de embeddings distinto"):
                await transport.embed("nomic-embed-text", ["texto"])

    async def test_accepts_implicit_latest_alias_from_runtime(self):
        transport = OllamaTransport("http://ollama:11434")
        with patch.object(transport, "_post_json", return_value={
            "model": "nomic-embed-text:latest", "embeddings": [[0.1, 0.2]],
        }):
            self.assertEqual(await transport.embed("nomic-embed-text", ["texto"]), [[0.1, 0.2]])


    def test_api_and_repository_embedder_share_settings_identity(self):
        from rag.embedder import OllamaEmbedder

        class Settings:
            embed_model = "nomic-embed-text"
            embed_dimension = 768

        api_identity = EmbeddingIdentity.from_settings(Settings())
        repository_embedder = OllamaEmbedder.from_settings(object(), Settings())
        self.assertEqual(repository_embedder.identity, api_identity)
        self.assertEqual(repository_embedder.dimension, api_identity.dimension)


if __name__ == "__main__":
    unittest.main()
