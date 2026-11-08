import secrets
from fastapi import Header, HTTPException
from api.config import settings


async def require_api_key(authorization: str | None = Header(default=None),
                          x_api_key: str | None = Header(default=None)):
    # La clave compartida no representa a un usuario ni autoriza un project_id concreto.
    # Nunca permitir que la API legacy evite reservas/liquidación del ledger.
    if settings.billing_enforcement_enabled:
        raise HTTPException(
            status_code=503,
            detail="Legacy API is unavailable while credit enforcement is enabled",
        )
    if not settings.legacy_api_enabled:
        raise HTTPException(status_code=503, detail="Legacy API is disabled")
    configured = settings.api_key
    if not configured or len(configured) < 32:
        raise HTTPException(status_code=503, detail="API key is not configured securely")
    supplied = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied or not secrets.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="Invalid API key")
