"""Comprobaciones seguras de preparación para el lanzamiento."""

from api.config import settings
from api.email_delivery import email_delivery_configured
from api.mfa import EnvironmentMfaKeyProvider, MfaError
from api.billing_result_crypto import EnvironmentResultKeyProvider, ResultEncryptionError


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

    billing = {
        "mode": "ledger" if settings.billing_enforcement_enabled else "shadow",
        "result_encryption_key": "not_required",
    }
    if settings.billing_enforcement_enabled:
        try:
            EnvironmentResultKeyProvider().active_key()
            billing["result_encryption_key"] = "configured"
        except (ResultEncryptionError, ValueError):
            billing["result_encryption_key"] = "missing"

    auth_ready = all(checks.values())
    billing_ready = (
        not settings.billing_enforcement_enabled
        or billing["result_encryption_key"] == "configured"
    )
    ready = auth_ready and billing_ready
    return {
        "status": "ready" if ready else "blocked",
        "checks": checks,
        "billing": billing,
    }
