import unittest
from rag.embedding_identity import EmbeddingIdentity
from rag.indexer import RepoIndexer
from rag.store import InMemoryVectorStore, QdrantStore

class Embedder:
    def __init__(self, model="nomic-embed-text", dimension=768):
        self.identity = EmbeddingIdentity(model, dimension)
        self.dimension = dimension

class StoreWithDimension:
    def __init__(self, dimension, identity=None):
        self.dim = dimension
        self.embedding_identity = identity

class Meta:
    pass

class RepoIndexerCompositionTests(unittest.TestCase):
    def test_rejects_embedder_store_dimension_mismatch_at_construction(self):
        with self.assertRaisesRegex(ValueError, "Dimensión.*incompatible"):
            RepoIndexer(Embedder(dimension=768), StoreWithDimension(1024), Meta())

    def test_accepts_matching_declared_model_and_dimension(self):
        identity = EmbeddingIdentity("nomic-embed-text", 768)
        self.assertIsNotNone(RepoIndexer(Embedder(), StoreWithDimension(768, identity), Meta()))

    def test_rejects_different_model_even_when_dimension_matches(self):
        identity = EmbeddingIdentity("mxbai-embed-large", 768)
        with self.assertRaisesRegex(ValueError, "Identidad de embeddings incompatible"):
            RepoIndexer(Embedder(), StoreWithDimension(768, identity), Meta())

    def test_rejects_different_dimension_in_declared_identity(self):
        identity = EmbeddingIdentity("nomic-embed-text", 1024)
        with self.assertRaisesRegex(ValueError, "Dimensión.*incompatible"):
            RepoIndexer(Embedder(), StoreWithDimension(1024, identity), Meta())

    def test_legacy_store_without_identity_remains_supported(self):
        self.assertIsNotNone(RepoIndexer(Embedder(), InMemoryVectorStore(), Meta()))

    def test_store_rejects_identity_dimension_mismatch(self):
        with self.assertRaisesRegex(ValueError, "no coincide"):
            QdrantStore("http://localhost:6333", "test", 768,
                        embedding_identity=EmbeddingIdentity("nomic", 1024))

if __name__ == "__main__":
    unittest.main()
