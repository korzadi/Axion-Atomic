"""Fingerprint canónico para idempotencia de solicitudes de inferencia."""
from __future__ import annotations

import hashlib
import json


class BillingRequestFingerprintError(ValueError):
    pass


def billing_request_fingerprint(
    *,
    user_id: str,
    project_id: str,
    model: str,
    messages: list[dict],
    temperature: float,
    max_output_tokens: int,
    policy_version: str,
) -> str:
    """Hash SHA-256 del contexto FINAL enviado a inferencia y su política."""
    if not all(isinstance(v, str) and v.strip() for v in
               (user_id, project_id, model, policy_version)):
        raise BillingRequestFingerprintError("Identidad, proyecto, modelo y política son obligatorios")
    if not isinstance(messages, list) or not messages:
        raise BillingRequestFingerprintError("Mensajes finales obligatorios")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or max_output_tokens < 1:
        raise BillingRequestFingerprintError("max_output_tokens inválido")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
        raise BillingRequestFingerprintError("temperature inválida")
    normalized = []
    for message in messages:
        if not isinstance(message, dict) or set(message) - {"role", "content"}:
            raise BillingRequestFingerprintError("Mensaje con campos no admitidos")
        role, content = message.get("role"), message.get("content")
        if role not in ("system", "user", "assistant") or not isinstance(content, str):
            raise BillingRequestFingerprintError("Mensaje inválido")
        normalized.append({"role": role, "content": content})
    payload = {
        "user_id": user_id, "project_id": project_id, "model": model,
        "messages": normalized, "temperature": float(temperature),
        "max_output_tokens": max_output_tokens, "policy_version": policy_version,
    }
    try:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise BillingRequestFingerprintError("No se pudo normalizar la solicitud") from exc
    return hashlib.sha256(encoded).hexdigest()
