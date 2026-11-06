"""Envelope versionado para persistir resultado y medición bajo el mismo ciphertext.

El caller debe cifrar los bytes devueltos con AesGcmResultCipher y guardarlos
mediante persist_encrypted_result. Este módulo no accede a claves ni a DB.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from api.billing_policy import UsageUnavailable, credits_for_usage

ENVELOPE_VERSION = 1


class ExecutionEnvelopeError(ValueError):
    """El envelope no cumple el contrato versionado."""


@dataclass(frozen=True)
class VerifiedExecutionEnvelope:
    content: str
    model: str
    prompt_tokens: int
    output_tokens: int
    input_weight: int
    output_weight: int
    credits: int
    policy_version: str


def _counter(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionEnvelopeError(f"{name} debe ser un entero no negativo")
    return value


def build_execution_envelope(
    result: Any,
    *,
    expected_model: str,
    policy_version: str,
    input_weight: int,
    output_weight: int,
) -> bytes:
    """Serializa resultado y prueba de medición en un único payload cifrable."""
    if not isinstance(expected_model, str) or not expected_model.strip():
        raise ExecutionEnvelopeError("expected_model inválido")
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise ExecutionEnvelopeError("policy_version inválida")
    if getattr(result, "requested_model", None) != expected_model:
        raise ExecutionEnvelopeError("El modelo solicitado no coincide")
    if getattr(result, "returned_model", None) != expected_model:
        raise ExecutionEnvelopeError("El modelo devuelto no coincide")
    if getattr(result, "done", None) is not True:
        raise ExecutionEnvelopeError("La inferencia no está finalizada")
    if getattr(result, "usage_source", None) != "ollama_response":
        raise UsageUnavailable("La fuente de medición no es verificable")
    content = getattr(result, "content", None)
    if not isinstance(content, str):
        raise ExecutionEnvelopeError("Contenido de respuesta inválido")
    prompt = _counter(getattr(result, "prompt_eval_count", None), "prompt_eval_count")
    output = _counter(getattr(result, "eval_count", None), "eval_count")
    input_weight = _counter(input_weight, "input_weight")
    output_weight = _counter(output_weight, "output_weight")
    credits = credits_for_usage(
        prompt, output, input_weight=input_weight, output_weight=output_weight
    )
    payload = {
        "version": ENVELOPE_VERSION,
        "content": content,
        "model": expected_model,
        "usage_source": "ollama_response",
        "prompt_tokens": prompt,
        "output_tokens": output,
        "input_weight": input_weight,
        "output_weight": output_weight,
        "credits": credits,
        "policy_version": policy_version,
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def parse_execution_envelope(data: bytes) -> VerifiedExecutionEnvelope:
    """Valida un envelope ya descifrado; no sustituye la autenticación AES-GCM."""
    if not isinstance(data, bytes) or not data:
        raise ExecutionEnvelopeError("Envelope vacío")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionEnvelopeError("Envelope JSON inválido") from exc
    required = {
        "version", "content", "model", "usage_source", "prompt_tokens",
        "output_tokens", "input_weight", "output_weight", "credits",
        "policy_version",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ExecutionEnvelopeError("Campos del envelope no coinciden con v1")
    if value["version"] != ENVELOPE_VERSION or isinstance(value["version"], bool):
        raise ExecutionEnvelopeError("Versión de envelope no soportada")
    if not isinstance(value["content"], str) or not isinstance(value["model"], str) or not value["model"]:
        raise ExecutionEnvelopeError("Respuesta o modelo inválido")
    if value["usage_source"] != "ollama_response":
        raise ExecutionEnvelopeError("Fuente de uso inválida")
    if not isinstance(value["policy_version"], str) or not value["policy_version"]:
        raise ExecutionEnvelopeError("Versión de política inválida")
    prompt = _counter(value["prompt_tokens"], "prompt_tokens")
    output = _counter(value["output_tokens"], "output_tokens")
    input_weight = _counter(value["input_weight"], "input_weight")
    output_weight = _counter(value["output_weight"], "output_weight")
    credits = _counter(value["credits"], "credits")
    expected = credits_for_usage(
        prompt, output, input_weight=input_weight, output_weight=output_weight
    )
    if credits != expected:
        raise ExecutionEnvelopeError("Los créditos no coinciden con los contadores")
    return VerifiedExecutionEnvelope(
        content=value["content"], model=value["model"],
        prompt_tokens=prompt, output_tokens=output,
        input_weight=input_weight, output_weight=output_weight,
        credits=credits, policy_version=value["policy_version"],
    )


def serialize_billing_execution_result(
    result: Any,
    *,
    expected_model: str,
    policy_version: str,
    input_weight: int,
    output_weight: int,
) -> bytes:
    """Adaptador listo para execute_durable_reserved_inference.serialize_result."""
    return build_execution_envelope(
        result,
        expected_model=expected_model,
        policy_version=policy_version,
        input_weight=input_weight,
        output_weight=output_weight,
    )


def deserialize_billing_execution_result(data: bytes) -> Any:
    """Adaptador para deserialize_result; devuelve un objeto compatible con el orquestador."""
    from types import SimpleNamespace

    verified = parse_execution_envelope(data)
    return SimpleNamespace(
        content=verified.content,
        requested_model=verified.model,
        returned_model=verified.model,
        done=True,
        prompt_eval_count=verified.prompt_tokens,
        eval_count=verified.output_tokens,
        usage_source="ollama_response",
        policy_version=verified.policy_version,
        input_weight=verified.input_weight,
        output_weight=verified.output_weight,
        actual_credits=verified.credits,
    )
