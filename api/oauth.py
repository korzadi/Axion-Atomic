"""OAuth 2.0 para Google OIDC y GitHub; los access tokens solo viven en memoria."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import text
from sqlalchemy.engine import Engine

PROVIDERS = ("google", "github")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def configured(settings, provider: str) -> bool:
    if provider == "google":
        return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret and settings.oauth_public_base_url)
    if provider == "github":
        return bool(settings.github_oauth_client_id and settings.github_oauth_client_secret and settings.oauth_public_base_url)
    return False


def begin(engine: Engine, provider: str, settings) -> str:
    if provider not in PROVIDERS or not configured(settings, provider):
        raise ValueError("Proveedor OAuth no configurado")
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO oauth_login_states(state_hash,provider,nonce,created_at,expires_at)
            VALUES(:hash,:provider,:nonce,:now,:expires)
        """), {"hash": digest(state), "provider": provider, "nonce": nonce,
               "now": now, "expires": now + timedelta(minutes=10)})
    callback = settings.oauth_public_base_url.rstrip("/") + "/auth/oauth/" + provider + "/callback"
    if provider == "google":
        params = {"client_id": settings.google_oauth_client_id, "redirect_uri": callback,
                  "response_type": "code", "scope": "openid email profile",
                  "state": state, "nonce": nonce, "prompt": "select_account"}
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    params = {"client_id": settings.github_oauth_client_id, "redirect_uri": callback,
              "scope": "read:user user:email", "state": state}
    return "https://github.com/login/oauth/authorize?" + urlencode(params)


def consume_state(engine: Engine, provider: str, state: str) -> str:
    if not isinstance(state, str) or not 20 <= len(state) <= 256:
        raise ValueError("Estado OAuth inválido")
    now, hashed = datetime.now(timezone.utc), digest(state)
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT nonce FROM oauth_login_states
            WHERE state_hash=:hash AND provider=:provider
              AND consumed_at IS NULL AND expires_at > :now FOR UPDATE
        """), {"hash": hashed, "provider": provider, "now": now}).mappings().first()
        if row is None:
            raise ValueError("Estado OAuth inválido o expirado")
        changed = conn.execute(text("""
            UPDATE oauth_login_states SET consumed_at=:now
            WHERE state_hash=:hash AND consumed_at IS NULL
        """), {"now": now, "hash": hashed})
        if changed.rowcount != 1:
            raise ValueError("Estado OAuth ya utilizado")
        return row["nonce"]


def provider_profile(provider: str, code: str, nonce: str, settings) -> dict:
    callback = settings.oauth_public_base_url.rstrip("/") + "/auth/oauth/" + provider + "/callback"
    with httpx.Client(timeout=12.0, follow_redirects=False) as client:
        if provider == "google":
            token_response = client.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": callback, "grant_type": "authorization_code"})
            token_response.raise_for_status()
            identity_token = token_response.json().get("id_token")
            if not isinstance(identity_token, str):
                raise ValueError("Google no devolvió token de identidad")
            parts = identity_token.split(".")
            if len(parts) != 3:
                raise ValueError("JWT de Google inválido")
            header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4)))
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise ValueError("Algoritmo JWT de Google no admitido")
            keys_response = client.get("https://www.googleapis.com/oauth2/v3/certs")
            keys_response.raise_for_status()
            jwk = next((key for key in keys_response.json().get("keys", [])
                        if key.get("kid") == header["kid"] and key.get("kty") == "RSA"), None)
            if jwk is None:
                raise ValueError("Clave de firma Google desconocida")
            decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            public_key = rsa.RSAPublicNumbers(int.from_bytes(decode(jwk["e"]), "big"),
                                              int.from_bytes(decode(jwk["n"]), "big")).public_key()
            public_key.verify(decode(parts[2]), (parts[0] + "." + parts[1]).encode("ascii"),
                              padding.PKCS1v15(), hashes.SHA256())
            audience = claims.get("aud")
            if audience != settings.google_oauth_client_id and not (
                isinstance(audience, list) and settings.google_oauth_client_id in audience
            ):
                raise ValueError("Audiencia Google inválida")
            if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
                raise ValueError("Emisor Google inválido")
            if claims.get("nonce") != nonce or claims.get("email_verified") not in (True, "true"):
                raise ValueError("Google no verificó el correo o nonce")
            if int(claims.get("exp", 0)) <= int(time.time()):
                raise ValueError("Token Google expirado")
            email, subject = claims.get("email"), claims.get("sub")
            name = claims.get("name") or (email or "").split("@")[0]
        elif provider == "github":
            token_response = client.post("https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={"code": code, "client_id": settings.github_oauth_client_id,
                      "client_secret": settings.github_oauth_client_secret, "redirect_uri": callback})
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not isinstance(access_token, str):
                raise ValueError("GitHub no autorizó el acceso")
            headers = {"Authorization": "Bearer " + access_token,
                       "Accept": "application/vnd.github+json",
                       "X-GitHub-Api-Version": "2022-11-28"}
            user_response = client.get("https://api.github.com/user", headers=headers)
            user_response.raise_for_status()
            profile = user_response.json()
            emails_response = client.get("https://api.github.com/user/emails", headers=headers)
            emails_response.raise_for_status()
            verified = [item for item in emails_response.json()
                        if item.get("verified") is True and item.get("primary") is True]
            if not verified:
                verified = [item for item in emails_response.json() if item.get("verified") is True]
            if not verified:
                raise ValueError("GitHub no proporcionó correo verificado")
            email, subject = verified[0]["email"], str(profile.get("id"))
            name = profile.get("name") or profile.get("login") or email.split("@")[0]
        else:
            raise ValueError("Proveedor OAuth no admitido")
    if not isinstance(email, str) or "@" not in email or not isinstance(subject, str) or not subject:
        raise ValueError("Perfil OAuth incompleto")
    return {"email": email.strip().casefold(), "subject": subject, "name": str(name)[:120]}


def resolve_user(engine: Engine, provider: str, profile: dict) -> dict:
    from api.auth import hash_password
    import uuid
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        linked = conn.execute(text("""
            SELECT u.id,u.email,u.display_name,u.status
            FROM oauth_identities i JOIN users u ON u.id=i.user_id
            WHERE i.provider=:provider AND i.provider_subject=:subject FOR UPDATE
        """), {"provider": provider, "subject": profile["subject"]}).mappings().first()
        if linked:
            if linked["status"] != "active":
                raise ValueError("Cuenta deshabilitada")
            return dict(linked)
        user = conn.execute(text("""
            SELECT id,email,display_name,status FROM users
            WHERE email_normalized=:email FOR UPDATE
        """), {"email": profile["email"]}).mappings().first()
        if user and user["status"] == "disabled":
            raise ValueError("Cuenta deshabilitada")
        if user:
            user_id, display_name = user["id"], user["display_name"]
            conn.execute(text("""
                UPDATE users SET status='active',email_verified_at=COALESCE(email_verified_at,:now),updated_at=:now
                WHERE id=:id
            """), {"id": user_id, "now": now})
        else:
            user_id, display_name = secrets.token_urlsafe(24), profile["name"]
            conn.execute(text("""
                INSERT INTO users(id,email,email_normalized,password_hash,display_name,status,email_verified_at,created_at,updated_at)
                VALUES(:id,:email,:email,:password,:name,'active',:now,:now,:now)
            """), {"id": user_id, "email": profile["email"],
                   "password": hash_password(secrets.token_urlsafe(40)),
                   "name": display_name, "now": now})
        conn.execute(text("""
            INSERT INTO oauth_identities(id,user_id,provider,provider_subject,email,created_at,updated_at)
            VALUES(:id,:user_id,:provider,:subject,:email,:now,:now)
        """), {"id": str(uuid.uuid4()), "user_id": user_id, "provider": provider,
               "subject": profile["subject"], "email": profile["email"], "now": now})
        return {"id": user_id, "email": profile["email"],
                "display_name": display_name, "status": "active"}
