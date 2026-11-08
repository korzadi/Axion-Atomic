"""Embeddings mediante el Ollama existente (/api/embed). Valida identidad y vectores."""
from typing import Protocol

from core.errors import TransportError
from rag.embedding_identity import EmbeddingIdentity
from rag.vector_contract import validate_embedding_batch


class Embedder(Protocol):
    dimension: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    def __init__(self, transport, model: str, dimension: int, batch_size: int = 16):
        self.transport, self.model, self.dimension, self.batch_size = transport, model, dimension, batch_size
        self.identity = EmbeddingIdentity(model, dimension)
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("El tamaño del lote de embeddings debe ser un entero positivo")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            vecs = await self.transport.embed(self.model, batch)
            try:
                out += validate_embedding_batch(vecs, len(batch), self.dimension)
            except ValueError as exc:
                raise TransportError(
                    f"El modelo {self.identity.model} devolvió embeddings incompatibles: {exc}",
                    retryable=False,
                ) from exc
        return out
