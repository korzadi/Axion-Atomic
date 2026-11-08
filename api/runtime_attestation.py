"""Atestación del artefacto Ollama exacto antes de una inferencia facturable.

No altera Ollama ni descarga modelos: compara el manifiesto declarado por el
operador con `/api/tags` y `/api/show`. Si falta cualquier identidad o no
coincide, la ejecución debe fallar cerrada antes de reservar créditos.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import httpx

from api.config import Settings, settings

CACHE_TTL_SECONDS = 300.0
SUPPORTED_TOKENIZER_ARCHITECTURES = {"qwen2_byte_fallback": "qwen2"}


class RuntimeAttestationError(RuntimeError):
    """El runtime no coincide con el manifiesto verificado o no está configurado."""


@dataclass(frozen=True)
class RuntimeIdentity:
    runtime_model: str
    model_digest: str
    template_sha256: str
    tokenizer_contract: str


_cache: dict[tuple[str, str, str, str, str], tuple[float, RuntimeIdentity]] = {}


def clear_attestation_cache() -> None:
    _cache.clear()


def _required(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeAttestationError(f"Falta la identidad verificada {name}")
    return value.strip()


def _normalize_digest(value: str) -> str:
    digest = value.strip().lower()
    if digest.startswith("sha256:"):
        digest = digest[7:]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise RuntimeAttestationError("El digest del modelo no es un SHA-256 válido")
    return "sha256:" + digest


def runtime_attestation_configured(current: Settings | None = None) -> bool:
    """Comprueba solo el manifiesto declarado; no consulta la red."""
    active = current or settings
    try:
        _normalize_digest(_required(getattr(active, "billing_runtime_model_digest", None), "BILLING_RUNTIME_MODEL_DIGEST"))
        template = _required(getattr(active, "billing_runtime_template_sha256", None), "BILLING_RUNTIME_TEMPLATE_SHA256").lower()
        if len(template) != 64 or any(char not in "0123456789abcdef" for char in template):
            return False
        contract = _required(getattr(active, "billing_tokenizer_contract", None), "BILLING_TOKENIZER_CONTRACT")
        return contract in SUPPORTED_TOKENIZER_ARCHITECTURES
    except RuntimeAttestationError:
        return False


def _template_sha256(template: str) -> str:
    if not isinstance(template, str) or not template.strip():
        raise RuntimeAttestationError("Ollama no devolvió la plantilla del modelo")
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


async def attest_runtime(current: Settings | None = None, *, force: bool = False) -> RuntimeIdentity:
    """Valida digest, plantilla y arquitectura contra el Ollama configurado.

    El resultado se cachea brevemente para no añadir dos peticiones HTTP a cada
    inferencia. Un fallo nunca se cachea.
    """
    active = current or settings
    model = _required(active.chat_model, "CHAT_MODEL")
    expected_digest = _normalize_digest(
        _required(getattr(active, "billing_runtime_model_digest", None), "BILLING_RUNTIME_MODEL_DIGEST")
    )
    expected_template = _required(
        getattr(active, "billing_runtime_template_sha256", None),
        "BILLING_RUNTIME_TEMPLATE_SHA256",
    ).lower()
    if len(expected_template) != 64 or any(char not in "0123456789abcdef" for char in expected_template):
        raise RuntimeAttestationError("BILLING_RUNTIME_TEMPLATE_SHA256 no es un SHA-256 válido")
    contract = _required(
        getattr(active, "billing_tokenizer_contract", None),
        "BILLING_TOKENIZER_CONTRACT",
    )
    expected_arch = SUPPORTED_TOKENIZER_ARCHITECTURES.get(contract)
    if expected_arch is None:
        raise RuntimeAttestationError("Contrato de tokenizer sin atestación soportada")

    cache_key = (active.ollama_base_url.rstrip("/"), model, expected_digest, expected_template, contract)
    now = time.monotonic()
    cached = _cache.get(cache_key)
    if not force and cached is not None and cached[0] > now:
        return cached[1]

    base = active.ollama_base_url.rstrip("/")
    timeout = min(float(getattr(active, "ollama_request_timeout_seconds", 30.0)), 30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        tags = await client.get(base + "/api/tags")
        tags.raise_for_status()
        try:
            models = tags.json().get("models")
        except (TypeError, ValueError):
            models = None
        if not isinstance(models, list):
            raise RuntimeAttestationError("Ollama devolvió un catálogo de modelos inválido")
        actual_digest = None
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("model")
            if isinstance(name, str) and name.strip() == model:
                actual_digest = item.get("digest")
                break
        if not isinstance(actual_digest, str) or not actual_digest.strip():
            raise RuntimeAttestationError("El modelo autorizado no está presente en Ollama")
        if _normalize_digest(actual_digest) != expected_digest:
            raise RuntimeAttestationError("El digest del modelo no coincide con el manifiesto")

        show = await client.post(base + "/api/show", json={"model": model})
        show.raise_for_status()
        try:
            payload = show.json()
        except (TypeError, ValueError):
            payload = None
        if not isinstance(payload, dict):
            raise RuntimeAttestationError("Ollama devolvió una identidad de modelo inválida")
        if _template_sha256(payload.get("template")) != expected_template:
            raise RuntimeAttestationError("La plantilla del modelo no coincide con el manifiesto")
        model_info = payload.get("model_info")
        architecture = model_info.get("general.architecture") if isinstance(model_info, dict) else None
        if architecture != expected_arch:
            raise RuntimeAttestationError("La arquitectura del modelo no corresponde al tokenizer declarado")

    identity = RuntimeIdentity(
        runtime_model=model,
        model_digest=expected_digest,
        template_sha256=expected_template,
        tokenizer_contract=contract,
    )
    _cache[cache_key] = (now + CACHE_TTL_SECONDS, identity)
    return identity
