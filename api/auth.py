"""Autenticación por sesiones opacas y autorización por proyecto."""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import text

from api.database import engine

SESSION_TTL_HOURS = 24


def now_utc():
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 256:
        raise ValueError("La contraseña debe tener entre 12 y 256 caracteres")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    enc = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return "scrypt$16384$8$1$" + enc(salt) + "$" + enc(digest)


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = stored.split("$")
        if algorithm != "scrypt":
            return False
        decode = base64.urlsafe_b64decode
        actual = hashlib.scrypt(password.encode(), salt=decode(salt), n=int(n),
                                r=int(r), p=int(p), dklen=len(decode(expected)))
        return hmac.compare_digest(actual, decode(expected))
    except (ValueError, TypeError):
        return False
