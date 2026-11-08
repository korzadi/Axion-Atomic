import math
import unittest

from core.errors import TransportError
from rag.embedder import OllamaEmbedder
from rag.embedding_identity import EmbeddingIdentity
from rag.vector_contract import validate_embedding_batch, validate_embedding_vector


class VectorContractTests(unittest.TestCase):
    def test_normalizes_finite_numeric_components(self):
        self.assertEqual(validate_embedding_vector([1, 2.5, 0, -3], 4), [1.0, 2.5, 0.0, -3.0])

    def test_rejects_wrong_dimension_and_invalid_dimension(self):
        for vector, dimension in (([1, 2], 3), ([1], 0), ([1], True), ("123", 3)):
            with self.subTest(vector=vector, dimension=dimension):
                with self.assertRaises(ValueError):
                    validate_embedding_vector(vector, dimension)

    def test_rejects_non_numeric_boolean_and_non_finite_components(self):
        for value in (True, "0.5", float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_embedding_vector([value], 1)

    def test_batch_checks_cardinality_before_returning(self):
        self.assertEqual(
            validate_embedding_batch([[1, 2], [3, 4]], 2, 2),
            [[1.0, 2.0], [3.0, 4.0]],
        )
        with self.assertRaises(ValueError):
            validate_embedding_batch([[1, 2]], 2, 2)


class StubTransport:
    def __init__(self, vectors):
        self.vectors = vectors

    async def embed(self, model, texts):
        return self.vectors


class OllamaEmbedderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_non_finite_batch_before_indexer_receives_vectors(self):
        embedder = OllamaEmbedder(StubTransport([[1.0, math.nan]]), "nomic", 2)
        with self.assertRaises(TransportError):
            await embedder.embed(["document"])

    async def test_rejects_wrong_batch_cardinality(self):
        embedder = OllamaEmbedder(StubTransport([]), "nomic", 2)
        with self.assertRaises(TransportError):
            await embedder.embed(["document"])

    async def test_returns_normalized_vectors(self):
        embedder = OllamaEmbedder(StubTransport([[1, 2]]), "nomic", 2)
        self.assertEqual(await embedder.embed(["document"]), [[1.0, 2.0]])

    async def test_exposes_canonical_embedding_identity(self):
        embedder = OllamaEmbedder(StubTransport([[1, 2]]), "nomic", 2)
        self.assertEqual(embedder.identity, EmbeddingIdentity("nomic:latest", 2))

    async def test_rejects_invalid_batch_size_at_construction(self):
        for batch_size in (0, -1, True):
            with self.subTest(batch_size=batch_size), self.assertRaises(ValueError):
                OllamaEmbedder(StubTransport([]), "nomic", 2, batch_size=batch_size)


if __name__ == "__main__":
    unittest.main()
