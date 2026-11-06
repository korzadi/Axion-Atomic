"""Serialización estable y validada de resultados Ollama para almacenamiento cifrado."""
from __future__ import annotations

import json
from api.ollama import InferenceResult


class InferenceResultCodecError(ValueError):
    pass


_FIELDS = (
    "content", "requested_model", "returned_model", "done",
    "prompt_eval_count", "eval_count", "total_duration_ns",
    "load_duration_ns", "prompt_eval_duration_ns", "eval_duration_ns",
    "usage_source",
)
_COUNTERS = (
    "prompt_eval_count", "eval_count", "total_duration_ns",
    "load_duration_ns", "prompt_eval_duration_ns", "eval_duration_ns",
)
_MAX_RESULT_BYTES = 2 * 1024 * 1024


def serialize_inference_result(result: InferenceResult) -> bytes:
    if not isinstance(result, InferenceResult):
        raise InferenceResultCodecError("Tipo de resultado no admitido")
    payload = {name: getattr(result, name) for name in _FIELDS}
    _validate(payload)
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise InferenceResultCodecError("No se pudo serializar el resultado") from exc
    if not encoded or len(encoded) > _MAX_RESULT_BYTES:
        raise InferenceResultCodecError("Resultado fuera del tamaño permitido")
    return encoded


def deserialize_inference_result(payload: bytes) -> InferenceResult:
    if not isinstance(payload, bytes) or not payload or len(payload) > _MAX_RESULT_BYTES:
        raise InferenceResultCodecError("Payload cifrado recuperado fuera del tamaño permitido")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InferenceResultCodecError("Payload de resultado inválido") from exc
    if not isinstance(data, dict) or set(data) != set(_FIELDS):
        raise InferenceResultCodecError("Esquema de resultado desconocido")
    _validate(data)
    return InferenceResult(**data)


def _validate(data: dict) -> None:
    if not isinstance(data.get("content"), str):
        raise InferenceResultCodecError("Contenido inválido")
    if not isinstance(data.get("requested_model"), str) or not data["requested_model"]:
        raise InferenceResultCodecError("Modelo solicitado inválido")
    returned = data.get("returned_model")
    if returned is not None and (not isinstance(returned, str) or not returned):
        raise InferenceResultCodecError("Modelo devuelto inválido")
    if data.get("done") is not None and type(data.get("done")) is not bool:
        raise InferenceResultCodecError("Estado done inválido")
    if data.get("usage_source") not in ("ollama_response", "unavailable"):
        raise InferenceResultCodecError("Fuente de medición inválida")
    for name in _COUNTERS:
        value = data.get(name)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise InferenceResultCodecError(f"Contador inválido: {name}")
