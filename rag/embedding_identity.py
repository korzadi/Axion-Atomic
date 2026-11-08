"""Identidad estable de modelos de embeddings compartida por los pipelines RAG."""
from dataclasses import dataclass


def canonical_model_name(model: str) -> str:
    """Normaliza únicamente el alias implícito de Ollama a su etiqueta :latest."""
    if not isinstance(model, str):
        raise ValueError("El modelo de embeddings debe ser una cadena")
    value = model.strip()
    if not value or any(char.isspace() for char in value):
        raise ValueError("El modelo de embeddings debe ser un nombre no vacío y sin espacios")
    return value if ":" in value else f"{value}:latest"


def same_model(left: str, right: str) -> bool:
    """Compara etiquetas Ollama sin confundir aliases :latest con modelos distintos."""
    return canonical_model_name(left) == canonical_model_name(right)


@dataclass(frozen=True)
class EmbeddingIdentity:
    """Identidad lógica de un espacio vectorial: modelo Ollama + dimensión."""

    model: str
    dimension: int

    def __post_init__(self):
        object.__setattr__(self, "model", canonical_model_name(self.model))
        if isinstance(self.dimension, bool) or not isinstance(self.dimension, int) or self.dimension <= 0:
            raise ValueError("La dimensión de embeddings debe ser un entero positivo")

    def compatible_with(self, other: "EmbeddingIdentity") -> bool:
        return isinstance(other, EmbeddingIdentity) and (
            self.model == other.model and self.dimension == other.dimension
        )


def require_compatible_embeddings(expected: EmbeddingIdentity, actual: EmbeddingIdentity) -> None:
    """Falla cerrado si dos pipelines pretenden compartir un espacio vectorial distinto."""
    if not isinstance(expected, EmbeddingIdentity) or not isinstance(actual, EmbeddingIdentity):
        raise TypeError("Se requieren identidades de embeddings válidas")
    if not expected.compatible_with(actual):
        raise ValueError(
            "Identidad de embeddings incompatible: "
            f"esperada {expected.model}/{expected.dimension}, "
            f"recibida {actual.model}/{actual.dimension}"
        )


def require_embedder_store_compatibility(embedder, store) -> None:
    """Validate identity at the actual RepoIndexer/store composition boundary."""
    embedder_dimension = getattr(embedder, "dimension", None)
    store_dimension = getattr(store, "dim", None)
    if store_dimension is not None and embedder_dimension != store_dimension:
        raise ValueError(
            "Dimensión de embeddings incompatible con el almacén vectorial: "
            f"embedder={embedder_dimension}, store={store_dimension}"
        )
    store_identity = getattr(store, "embedding_identity", None)
    embedder_identity = getattr(embedder, "identity", None)
    if store_identity is not None:
        if not isinstance(store_identity, EmbeddingIdentity):
            raise TypeError("El almacén declara una identidad de embeddings inválida")
        if not isinstance(embedder_identity, EmbeddingIdentity):
            raise ValueError("El embedder debe declarar su identidad para usar este almacén")
        require_compatible_embeddings(store_identity, embedder_identity)
