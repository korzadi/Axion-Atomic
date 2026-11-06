"""Estimación de tokens. Es una HEURÍSTICA conservadora para presupuestar contexto.
El uso real lo informa Ollama (prompt_eval_count / eval_count) y es lo que se registra en las métricas."""
import math

CHARS_PER_TOKEN = 3.2  # conservador para código; el texto natural suele dar más caracteres por token
MESSAGE_OVERHEAD = 4


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0


def estimate_messages(messages: list[dict]) -> int:
    return sum(estimate_tokens(m.get("content", "")) + MESSAGE_OVERHEAD for m in messages)
