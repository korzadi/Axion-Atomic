"""Embeddings mediante el Ollama existente (/api/embed). Valida cantidad y dimensión de los vectores."""
from typing import Protocol

from core.errors import TransportError
from rag.vector_contract import validate_embedding_batch


class Embedder(Protocol):
    dimension: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    def __init__(self, transport, model: str, dimension: int, batch_size: int = 16):
        self.transport, self.model, self.dimension, self.batch_size = transport, model, dimension, batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            vecs = await self.transport.embed(self.model, batch)
            try:
                out += validate_embedding_batch(vecs, len(batch), self.dimension)
            except ValueError as exc:
                raise TransportError(
                    f"El modelo {self.model} devolvió embeddings incompatibles: {exc}",
                    retryable=False,
                ) from exc
        return out
