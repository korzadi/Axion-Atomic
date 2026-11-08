"""Contrato compartido para vectores de embeddings antes de persistirlos o consultarlos."""
import math
from numbers import Real


def validate_embedding_vector(vector, dimension: int) -> list[float]:
    """Valida dimensión y componentes finitos; devuelve valores float normalizados."""
    if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
        raise ValueError("La dimensión de embedding debe ser un entero positivo")
    if not isinstance(vector, (list, tuple)) or len(vector) != dimension:
        raise ValueError("Ollama devolvió una dimensión de embedding inesperada")
    normalized = []
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError("Ollama devolvió un componente de embedding inválido")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Ollama devolvió un componente de embedding no finito")
        normalized.append(number)
    return normalized


def validate_embedding_batch(vectors, expected_count: int, dimension: int) -> list[list[float]]:
    """Valida cardinalidad y cada vector de un lote antes de indexarlo."""
    if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 0:
        raise ValueError("La cantidad esperada de embeddings no es válida")
    if not isinstance(vectors, list) or len(vectors) != expected_count:
        raise ValueError("Ollama devolvió una cantidad de embeddings inesperada")
    return [validate_embedding_vector(vector, dimension) for vector in vectors]
