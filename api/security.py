import secrets
from fastapi import Header, HTTPException
from api.config import settings

async def require_api_key(authorization: str | None = Header(default=None),
                          x_api_key: str | None = Header(default=None)):
    supplied = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied or not secrets.compare_digest(supplied, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
