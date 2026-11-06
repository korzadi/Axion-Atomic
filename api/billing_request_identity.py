"""Identidad estable de una solicitud HTTP idempotente."""
from __future__ import annotations

import hashlib
import json
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
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ValueError("temperature inválida")
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
