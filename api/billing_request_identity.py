"""Identidad estable de una solicitud HTTP idempotente."""
from __future__ import annotations

import hashlib
import json
import math
import uuid


# Namespace fijo del producto; no depende de datos secretos ni del proceso.
_REQUEST_NAMESPACE = uuid.UUID("7cb3f0c0-8c43-4f6b-9a3a-6d2efb7a0f31")


class InvalidIdempotencyKey(ValueError):
    pass


def stable_request_id(*, user_id: str, idempotency_key: str) -> str:
    """Misma identidad de usuario/clave produce siempre el mismo UUID."""
    if not isinstance(user_id, str) or not user_id.strip() or len(user_id) > 256:
        raise ValueError("user_id inválido")
    if not isinstance(idempotency_key, str):
        raise InvalidIdempotencyKey("Idempotency-Key debe ser texto")
    if not 1 <= len(idempotency_key) <= 200:
        raise InvalidIdempotencyKey("Idempotency-Key debe tener entre 1 y 200 caracteres")
    if any(ord(char) < 0x21 or ord(char) > 0x7E for char in idempotency_key):
        raise InvalidIdempotencyKey("Idempotency-Key debe usar caracteres ASCII imprimibles sin espacios")
    # El UUID no revela la clave original ni cambia entre reintentos.
    return str(uuid.uuid5(_REQUEST_NAMESPACE, f"{user_id}\0{idempotency_key}"))



def request_payload_sha256(
    *,
    project_id: str,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    policy_version: str,
) -> str:
    """Fingerprint canónico para detectar reuso de clave con payload distinto."""
    if not isinstance(project_id, str) or not project_id.strip() or len(project_id) > 200:
        raise ValueError("project_id inválido")
    if not isinstance(model, str) or not model.strip() or len(model) > 128:
        raise ValueError("model inválido")
    if not isinstance(policy_version, str) or not policy_version.strip() or len(policy_version) > 128:
        raise ValueError("policy_version inválida")
    if not isinstance(messages, list) or not messages or len(messages) > 100:
        raise ValueError("messages inválidos")
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not math.isfinite(temperature)
        or not 0 <= temperature <= 2
    ):
        raise ValueError("temperature debe ser un número finito entre 0 y 2")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 8192:
        raise ValueError("max_tokens inválido")
    payload = {
        "project_id": project_id,
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "policy_version": policy_version,
    }
    try:
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Payload no serializable de forma canónica") from exc
    return hashlib.sha256(canonical).hexdigest()


def attested_request_payload_sha256(
    *,
    project_id: str,
    public_model: str,
    runtime_model: str,
    model_digest: str,
    template_sha256: str,
    tokenizer_id: str,
    effective_messages: list[dict],
    temperature: float,
    max_tokens: int,
    policy_version: str,
) -> str:
    """Fingerprint estricto de la inferencia efectiva y su identidad de runtime.

    effective_messages debe ser la lista FINAL construida por el servidor,
    incluyendo system prompt e información RAG. Las identidades de runtime
    son obligatorias. Esta función SOLO las incorpora al hash: no demuestra
    que sean verdaderas ni verifica firmas/digests. El caller debe obtenerlas
    de un manifiesto de runtime confiable antes de considerar una ejecución
    elegible para facturación.
    """
    required = {
        "runtime_model": runtime_model,
        "model_digest": model_digest,
        "template_sha256": template_sha256,
        "tokenizer_id": tokenizer_id,
    }
    for name, value in required.items():
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError(f"{name} requiere una identidad verificada")
    if not isinstance(effective_messages, list) or not effective_messages:
        raise ValueError("effective_messages debe contener el prompt final del servidor")

    base = request_payload_sha256(
        project_id=project_id,
        model=public_model,
        messages=effective_messages,
        temperature=temperature,
        max_tokens=max_tokens,
        policy_version=policy_version,
    )
    attestation = {
        "base_payload_sha256": base,
        "runtime_model": runtime_model,
        "model_digest": model_digest,
        "template_sha256": template_sha256,
        "tokenizer_id": tokenizer_id,
    }
    canonical = json.dumps(
        attestation, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
