"""Comprobaciones seguras de preparación para el lanzamiento."""

from api.config import settings
from api.email_delivery import email_delivery_configured
from api.mfa import EnvironmentMfaKeyProvider, MfaError
from api.billing_result_crypto import EnvironmentResultKeyProvider, ResultEncryptionError
from api.runtime_attestation import runtime_attestation_configured


def auth_readiness() -> dict:
    """Expone solo estados booleanos/modos; nunca devuelve secretos."""
    checks = {
        "authentication_enabled": bool(settings.auth_enabled),
        "transactional_email": email_delivery_configured(settings),
        "https_cookie": bool(settings.auth_cookie_secure),
        "public_https_origin": bool(settings.oauth_public_base_url),
        "mfa_encryption_key": False,
    }
    if settings.auth_enabled:
        try:
            EnvironmentMfaKeyProvider().active_key()
            checks["mfa_encryption_key"] = True
        except (MfaError, ValueError):
            checks["mfa_encryption_key"] = False

    billing_enabled = bool(getattr(settings, "billing_enforcement_enabled", False))
    billing = {
        "mode": "ledger" if billing_enabled else "shadow",
        # /workspace/chat/completions ya usa reserva, claim, cifrado y settlement.
        "chat_execution": "integrated",
        "runtime_attestation": "not_required",
        "result_encryption_key": "not_required",
    }
    if billing_enabled:
        try:
            EnvironmentResultKeyProvider().active_key()
            billing["result_encryption_key"] = "configured"
        except (ResultEncryptionError, ValueError):
            billing["result_encryption_key"] = "missing"
        billing["runtime_attestation"] = (
            "configured" if runtime_attestation_configured(settings) else "missing"
        )

    auth_ready = all(checks.values())
    # Ledger exige clave dedicada y manifiesto verificado del artefacto Ollama.
    # La ruta heredada /v1 sigue fuera de la facturación multiusuario.
    billing_ready = (
        not billing_enabled
        or (
            billing["result_encryption_key"] == "configured"
            and billing["runtime_attestation"] == "configured"
            and billing["chat_execution"] == "integrated"
        )
    )
    ready = auth_ready and billing_ready
    return {
        "status": "ready" if ready else "blocked",
        "checks": checks,
        "billing": billing,
    }
