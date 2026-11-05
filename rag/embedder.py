"""Embeddings mediante el Ollama existente (/api/embed). Valida cantidad y dimensión de los vectores."""
from typing import Protocol

from core.errors import TransportError


class Embedder(Protocol):
    dimension: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    def __init__(self, transport, model: str, dimension: int, batch_size: int = 16):
        self.transport, self.model, self.dimension, self.batch_size = transport, model, dimension, batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vecs = await self.transport.embed(self.model, texts[i:i + self.batch_size])
            for v in vecs:
                if len(v) != self.dimension:
                    raise TransportError(f"El modelo {self.model} devolvió dimensión {len(v)}, se esperaba {self.dimension}", retryable=False)
            out += vecs
        return out
