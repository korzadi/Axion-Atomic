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

def create_user(email: str, password: str, role: str = "member") -> str:
    email = email.strip().lower()
    if len(email) > 254 or "@" not in email or role not in ("admin", "member"):
        raise ValueError("Datos de usuario inválidos")
    user_id = secrets.token_hex(16)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO axion_users(id,email,password_hash,role,active,created_at) "
            "VALUES (:id,:email,:password_hash,:role,true,:created_at)"
        ), {"id": user_id, "email": email, "password_hash": hash_password(password),
            "role": role, "created_at": now_utc()})
    return user_id


def bootstrap_admin(email: str, password: str) -> str:
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(918273645)"))
        count = conn.execute(text("SELECT COUNT(*) FROM axion_users")).scalar_one()
        if count:
            raise ValueError("El bootstrap ya fue utilizado")
        email = email.strip().lower()
        if len(email) > 254 or "@" not in email:
            raise ValueError("Correo inválido")
        user_id = secrets.token_hex(16)
        conn.execute(text(
            "INSERT INTO axion_users(id,email,password_hash,role,active,created_at) "
            "VALUES (:id,:email,:password_hash,'admin',true,:created_at)"
        ), {"id": user_id, "email": email, "password_hash": hash_password(password),
            "created_at": now_utc()})
        return user_id


def login(email: str, password: str):
    email = email.strip().lower()
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT id,password_hash,active FROM axion_users WHERE email=:email"
        ), {"email": email}).mappings().first()
        if not row or not row["active"] or not verify_password(password, row["password_hash"]):
            raise ValueError("Credenciales incorrectas")
        token = secrets.token_urlsafe(32)
        expires = now_utc() + timedelta(hours=SESSION_TTL_HOURS)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        conn.execute(text(
            "INSERT INTO axion_sessions(token_hash,user_id,expires_at,created_at) "
            "VALUES (:token_hash,:user_id,:expires_at,:created_at)"
        ), {"token_hash": token_hash, "user_id": row["id"], "expires_at": expires, "created_at": now_utc()})
        return token, expires
