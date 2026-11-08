from dataclasses import dataclass
from typing import Any, Literal

import httpx

from api.config import settings
from api.capacity import BoundedInferenceGate
from api.rcache import get_embedding, set_embedding
from rag.embedding_identity import EmbeddingIdentity, same_model
from rag.vector_contract import validate_embedding_vector

# Un solo turno pesado a la vez protege la RAM/CPU del VPS inicial.
ollama_gate = BoundedInferenceGate(
    max_concurrent=settings.ollama_max_concurrent,
    max_waiting=settings.ollama_max_waiting,
    wait_timeout=settings.ollama_queue_timeout_seconds,
)


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
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def parse_chat_response(data: dict[str, Any], requested_model: str) -> InferenceResult:
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ValueError("Respuesta de Ollama sin message.content válido")
    prompt_count = _non_negative_int(data.get("prompt_eval_count"))
    output_count = _non_negative_int(data.get("eval_count"))
    usage_source: Literal["ollama_response", "unavailable"] = (
        "ollama_response" if prompt_count is not None and output_count is not None else "unavailable"
    )
    returned_model = data.get("model")
    if not isinstance(returned_model, str) or not returned_model:
        returned_model = None
    if returned_model == f"{requested_model}:latest" and ":" not in requested_model:
        returned_model = requested_model
    elif requested_model == f"{returned_model}:latest" and ":" not in returned_model:
        returned_model = requested_model
    done = data.get("done") if isinstance(data.get("done"), bool) else None
    return InferenceResult(
        content=content, requested_model=requested_model, returned_model=returned_model,
        done=done, prompt_eval_count=prompt_count, eval_count=output_count,
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
    async with ollama_gate.slot():
        async with httpx.AsyncClient(timeout=settings.ollama_request_timeout_seconds) as client:
            response = await client.post(
                settings.ollama_base_url.rstrip("/") + "/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    return parse_chat_response(data, requested_model=settings.chat_model)


async def chat(messages, temperature=0.2, max_tokens=2048):
    """Devuelve texto solo si Ollama confirma el modelo autorizado y una inferencia completa."""
    result = await chat_with_usage(messages, temperature, max_tokens)
    if result.requested_model != settings.chat_model or result.returned_model != settings.chat_model:
        raise RuntimeError("El modelo ejecutado no coincide con el modelo autorizado")
    if result.done is not True:
        raise RuntimeError("La inferencia no terminó correctamente")
    return result.content


async def embed(value: str):
    identity = EmbeddingIdentity.from_settings(settings)
    # La clave usa identidad canónica: aliases sin etiqueta y :latest comparten
    # espacio de caché, mientras modelos/dimensiones diferentes nunca colisionan.
    cached = await get_embedding(identity.model, identity.dimension, value)
    if cached is not None:
        return validate_embedding_vector(cached, identity.dimension)
    async with ollama_gate.slot():
        async with httpx.AsyncClient(timeout=settings.ollama_request_timeout_seconds) as client:
            response = await client.post(
                settings.ollama_base_url.rstrip("/") + "/api/embeddings",
                json={"model": settings.embed_model.strip(), "prompt": value},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or "embedding" not in payload:
                raise ValueError("Respuesta de Ollama sin embedding válido")
            returned_model = payload.get("model")
            if returned_model is not None and (
                not isinstance(returned_model, str) or not same_model(returned_model, identity.model)
            ):
                raise ValueError("Ollama devolvió un modelo de embeddings distinto al solicitado")
            vector = payload["embedding"]
    vector = validate_embedding_vector(vector, identity.dimension)
    await set_embedding(identity.model, identity.dimension, value, vector)
    return vector


async def configured_chat_model_available() -> bool:
    """Comprueba en Ollama que el modelo configurado existe realmente en el runtime."""
    async with httpx.AsyncClient(timeout=min(settings.ollama_request_timeout_seconds, 10.0)) as client:
        response = await client.get(settings.ollama_base_url.rstrip("/") + "/api/tags")
        response.raise_for_status()
        payload = response.json()
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise ValueError("Ollama devolvió un catálogo de modelos inválido")
    names = {
        item.get("name") for item in models
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    configured = settings.chat_model.strip()
    if ":" not in configured:
        return configured in names or f"{configured}:latest" in names
    return configured in names
