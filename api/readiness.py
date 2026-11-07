"""Comprobaciones seguras de configuración para habilitar cuentas en producción."""

from api.config import settings
from api.email_delivery import email_delivery_configured
from api.mfa import EnvironmentMfaKeyProvider, MfaError


def auth_readiness() -> dict:
    """Expone solo booleanos; nunca devuelve secretos ni valores de configuración."""
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
    ready = all(checks.values())
    return {"status": "ready" if ready else "blocked", "checks": checks}
