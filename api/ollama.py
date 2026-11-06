from dataclasses import dataclass
from typing import Any, Literal

import httpx

from api.config import settings


@dataclass(frozen=True)
class InferenceResult:
    """Resultado de inferencia y contadores reportados por Ollama."""

    content: str
    requested_model: str
    returned_model: str | None
    done: bool | None
    prompt_eval_count: int | None
    eval_count: int | None
    total_duration_ns: int | None
    load_duration_ns: int | None
    prompt_eval_duration_ns: int | None
    eval_duration_ns: int | None
    usage_source: Literal["ollama_response", "unavailable"]


def _non_negative_int(value: Any) -> int | None:
    # bool es subtipo de int en Python, pero no es un contador válido.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def parse_chat_response(data: dict[str, Any], requested_model: str) -> InferenceResult:
    """Normaliza una respuesta /api/chat sin inventar contadores ausentes."""
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ValueError("Respuesta de Ollama sin message.content válido")

    prompt_count = _non_negative_int(data.get("prompt_eval_count"))
    output_count = _non_negative_int(data.get("eval_count"))
    usage_source: Literal["ollama_response", "unavailable"] = (
        "ollama_response"
        if prompt_count is not None and output_count is not None
        else "unavailable"
    )
    returned_model = data.get("model")
    if not isinstance(returned_model, str) or not returned_model:
        returned_model = None
    done = data.get("done") if isinstance(data.get("done"), bool) else None

    return InferenceResult(
        content=content,
        requested_model=requested_model,
        returned_model=returned_model,
        done=done,
        prompt_eval_count=prompt_count,
        eval_count=output_count,
        total_duration_ns=_non_negative_int(data.get("total_duration")),
        load_duration_ns=_non_negative_int(data.get("load_duration")),
        prompt_eval_duration_ns=_non_negative_int(data.get("prompt_eval_duration")),
        eval_duration_ns=_non_negative_int(data.get("eval_duration")),
        usage_source=usage_source,
    )


async def chat_with_usage(messages, temperature=0.2, max_tokens=2048) -> InferenceResult:
    payload = {
        "model": settings.chat_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": settings.num_ctx,
        },
    }
    async with httpx.AsyncClient(timeout=240) as client:
        response = await client.post(
            settings.ollama_base_url.rstrip("/") + "/api/chat",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    return parse_chat_response(data, requested_model=settings.chat_model)


async def chat(messages, temperature=0.2, max_tokens=2048):
    """Compatibilidad con consumidores existentes que esperan solo texto."""
    result = await chat_with_usage(messages, temperature, max_tokens)
    return result.content


async def embed(value: str):
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            settings.ollama_base_url.rstrip("/") + "/api/embeddings",
            json={"model": settings.embed_model, "prompt": value},
        )
        response.raise_for_status()
        return response.json()["embedding"]
