"""Persistencia transaccional MFA.

Las funciones consumen contadores TOTP, desafíos y códigos de recuperación bajo
bloqueos PostgreSQL. La API de autenticación debe crear sesión solo después de
que verify_login_challenge devuelva True.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, text

from api.mfa import (
    AesGcmTotpCipher,
    EncryptedTotpSecret,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    matching_totp_counter,
)

CHALLENGE_TTL = timedelta(minutes=5)
MAX_CHALLENGE_ATTEMPTS = 5


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def begin_enrollment(*, engine: Engine, cipher: AesGcmTotpCipher, user_id: str) -> str:
    """Crea o renueva solo un enrolamiento pendiente; nunca sustituye MFA activo."""
    secret = generate_totp_secret()
    encrypted = cipher.encrypt(secret, user_id=user_id)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO user_mfa_credentials (
                user_id, state, pending_secret_ciphertext, pending_secret_nonce,
                pending_secret_key_id, created_at, updated_at
            ) VALUES (
                :user_id, 'pending', :ciphertext, :nonce, :key_id, :now, :now
            )
            ON CONFLICT (user_id) DO UPDATE SET
                state='pending',
                pending_secret_ciphertext=EXCLUDED.pending_secret_ciphertext,
                pending_secret_nonce=EXCLUDED.pending_secret_nonce,
                pending_secret_key_id=EXCLUDED.pending_secret_key_id,
                secret_ciphertext=NULL, secret_nonce=NULL, secret_key_id=NULL,
                last_accepted_counter=-1, enabled_at=NULL, updated_at=EXCLUDED.updated_at
            WHERE user_mfa_credentials.state='pending'
        """), {
            "user_id": user_id, "ciphertext": encrypted.ciphertext,
            "nonce": encrypted.nonce, "key_id": encrypted.key_id, "now": now,
        })
        if result.rowcount != 1:
            raise ValueError("MFA ya está activo; desactívalo mediante un flujo verificado antes de reenrolar")
        conn.execute(text("""
            INSERT INTO user_mfa_audit_events(id,user_id,action,created_at)
            VALUES(:id,:user_id,'enrollment_started',:now)
        """), {"id": uuid.uuid4(), "user_id": user_id, "now": now})
    return secret


def confirm_enrollment(
    *, engine: Engine, cipher: AesGcmTotpCipher, user_id: str, code: str,
    now: datetime | None = None,
) -> list[str]:
    """Activa MFA y emite códigos una sola vez, dentro de una transacción."""
    instant = now or datetime.now(timezone.utc)
    timestamp = int(instant.timestamp())
    recovery_codes = generate_recovery_codes()
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT state, pending_secret_ciphertext, pending_secret_nonce,
                   pending_secret_key_id
            FROM user_mfa_credentials WHERE user_id=:user_id FOR UPDATE
        """), {"user_id": user_id}).mappings().first()
        if row is None or row["state"] != "pending":
            raise ValueError("No existe un enrolamiento MFA pendiente")
        encrypted = EncryptedTotpSecret(
            ciphertext=bytes(row["pending_secret_ciphertext"]),
            nonce=bytes(row["pending_secret_nonce"]),
            key_id=row["pending_secret_key_id"],
        )
        secret = cipher.decrypt(encrypted, user_id=user_id)
        counter = matching_totp_counter(secret, code, now=timestamp, window=1)
        if counter is None:
            raise ValueError("Código MFA inválido o expirado")
        conn.execute(text("""
            UPDATE user_mfa_credentials SET
                state='enabled',
                secret_ciphertext=pending_secret_ciphertext,
                secret_nonce=pending_secret_nonce,
                secret_key_id=pending_secret_key_id,
                pending_secret_ciphertext=NULL,
                pending_secret_nonce=NULL,
                pending_secret_key_id=NULL,
                last_accepted_counter=:counter,
                enabled_at=:now,
                updated_at=:now
            WHERE user_id=:user_id AND state='pending'
        """), {"user_id": user_id, "counter": counter, "now": instant})
        for recovery_code in recovery_codes:
            conn.execute(text("""
                INSERT INTO user_mfa_recovery_codes(id,user_id,code_hash,created_at)
                VALUES(:id,:user_id,:code_hash,:now)
            """), {
                "id": uuid.uuid4(), "user_id": user_id,
                "code_hash": hash_recovery_code(recovery_code), "now": instant,
            })
        conn.execute(text("""
            INSERT INTO user_mfa_audit_events(id,user_id,action,created_at)
            VALUES(:id,:user_id,'enrollment_confirmed',:now)
        """), {"id": uuid.uuid4(), "user_id": user_id, "now": instant})
    return recovery_codes


def issue_login_challenge(
    *, engine: Engine, user_id: str, purpose: str = "login",
    now: datetime | None = None,
) -> str:
    """Emite un token opaco temporal; solo su hash se conserva en DB."""
    if purpose not in ("login", "oauth"):
        raise ValueError("Propósito de desafío no válido")
    instant = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    with engine.begin() as conn:
        enabled = conn.execute(text("""
            SELECT 1 FROM user_mfa_credentials
            WHERE user_id=:user_id AND state='enabled'
        """), {"user_id": user_id}).scalar_one_or_none()
        if not enabled:
            raise ValueError("MFA no está habilitado para esta cuenta")
        conn.execute(text("""
            INSERT INTO auth_mfa_challenges(
                id,user_id,challenge_hash,purpose,expires_at,created_at
            ) VALUES(:id,:user_id,:challenge_hash,:purpose,:expires_at,:now)
        """), {
            "id": uuid.uuid4(), "user_id": user_id, "challenge_hash": _digest(token),
            "purpose": purpose, "expires_at": instant + CHALLENGE_TTL, "now": instant,
        })
    return token


def verify_login_challenge(
    *, engine: Engine, cipher: AesGcmTotpCipher, challenge_token: str, code: str,
    now: datetime | None = None,
) -> str | None:
    """Consume desafío y segundo factor atómicamente; devuelve user_id o None.

    El llamador solo puede emitir la sesión si recibe user_id. No invocar desde
    un flujo que ya haya creado una sesión de primer factor.
    """
    instant = now or datetime.now(timezone.utc)
    with engine.begin() as conn:
        challenge = conn.execute(text("""
            SELECT id,user_id,purpose,expires_at,attempts,consumed_at
            FROM auth_mfa_challenges WHERE challenge_hash=:challenge_hash FOR UPDATE
        """), {"challenge_hash": _digest(challenge_token)}).mappings().first()
        if (
            challenge is None or challenge["consumed_at"] is not None
            or challenge["expires_at"] <= instant
            or challenge["attempts"] >= MAX_CHALLENGE_ATTEMPTS
        ):
            return None
        user_id = challenge["user_id"]
        credential = conn.execute(text("""
            SELECT secret_ciphertext,secret_nonce,secret_key_id,last_accepted_counter
            FROM user_mfa_credentials
            WHERE user_id=:user_id AND state='enabled' FOR UPDATE
        """), {"user_id": user_id}).mappings().first()
        if credential is None:
            return None

        accepted = False
        counter = None
        recovery_row = None
        if code.isdigit() and len(code) == 6:
            encrypted = EncryptedTotpSecret(
                ciphertext=bytes(credential["secret_ciphertext"]),
                nonce=bytes(credential["secret_nonce"]),
                key_id=credential["secret_key_id"],
            )
            secret = cipher.decrypt(encrypted, user_id=user_id)
            counter = matching_totp_counter(
                secret, code, now=int(instant.timestamp()),
                last_accepted_counter=credential["last_accepted_counter"], window=1,
            )
            accepted = counter is not None
        else:
            try:
                code_hash = hash_recovery_code(code)
            except ValueError:
                code_hash = None
            if code_hash:
                recovery_row = conn.execute(text("""
                    SELECT id FROM user_mfa_recovery_codes
                    WHERE user_id=:user_id AND code_hash=:code_hash AND used_at IS NULL
                    FOR UPDATE
                """), {"user_id": user_id, "code_hash": code_hash}).mappings().first()
                accepted = recovery_row is not None

        if not accepted:
            conn.execute(text("""
                UPDATE auth_mfa_challenges SET attempts=attempts+1 WHERE id=:id
            """), {"id": challenge["id"]})
            conn.execute(text("""
                INSERT INTO user_mfa_audit_events(id,user_id,action,created_at)
                VALUES(:id,:user_id,'challenge_failed',:now)
            """), {"id": uuid.uuid4(), "user_id": user_id, "now": instant})
            return None

        if counter is not None:
            conn.execute(text("""
                UPDATE user_mfa_credentials
                SET last_accepted_counter=:counter,updated_at=:now
                WHERE user_id=:user_id
            """), {"counter": counter, "now": instant, "user_id": user_id})
            action = "challenge_succeeded"
        else:
            conn.execute(text("""
                UPDATE user_mfa_recovery_codes SET used_at=:now WHERE id=:id AND used_at IS NULL
            """), {"now": instant, "id": recovery_row["id"]})
            action = "recovery_code_used"
        conn.execute(text("""
            UPDATE auth_mfa_challenges SET consumed_at=:now WHERE id=:id AND consumed_at IS NULL
        """), {"now": instant, "id": challenge["id"]})
        conn.execute(text("""
            INSERT INTO user_mfa_audit_events(id,user_id,action,created_at)
            VALUES(:id,:user_id,:action,:now)
        """), {"id": uuid.uuid4(), "user_id": user_id, "action": action, "now": instant})
        return user_id
