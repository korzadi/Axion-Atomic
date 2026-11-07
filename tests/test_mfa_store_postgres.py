"""Pruebas de integración MFA contra PostgreSQL efímero del workflow CI."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

from api.mfa import AesGcmTotpCipher, hash_recovery_code, totp_at
from api.mfa_store import (
    begin_enrollment,
    confirm_enrollment,
    issue_login_challenge,
    verify_login_challenge,
)


class TestKeyProvider:
    def active_key(self):
        return "ci-mfa-key-v1", b"m" * 32

    def get_key(self, key_id):
        if key_id != "ci-mfa-key-v1":
            raise KeyError(key_id)
        return b"m" * 32


def test_mfa_enrollment_totp_replay_recovery_and_expiry_are_transactional():
    engine = create_engine(DATABASE_URL, future=True)
    user_id = "mfa-ci-" + uuid.uuid4().hex
    cipher = AesGcmTotpCipher(TestKeyProvider())
    now = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO users(id,email,email_normalized,password_hash,display_name,status)
                VALUES(:id,:email,:normalized,'test-only-hash','MFA CI','active')
            """), {
                "id": user_id,
                "email": user_id + "@example.invalid",
                "normalized": user_id + "@example.invalid",
            })

        secret = begin_enrollment(engine=engine, cipher=cipher, user_id=user_id)
        recovery_codes = confirm_enrollment(
            engine=engine, cipher=cipher, user_id=user_id,
            code=totp_at(secret, int(now.timestamp())), now=now,
        )
        assert len(recovery_codes) == 10

        login_now = now + timedelta(seconds=30)
        challenge = issue_login_challenge(
            engine=engine, user_id=user_id, purpose="login", now=login_now,
        )
        assert verify_login_challenge(
            engine=engine, cipher=cipher, challenge_token=challenge,
            code=totp_at(secret, int(login_now.timestamp())),
            expected_purpose="oauth", now=login_now,
        ) is None
        assert verify_login_challenge(
            engine=engine, cipher=cipher, challenge_token=challenge,
            code=totp_at(secret, int(login_now.timestamp())),
            expected_purpose="login", now=login_now,
        ) == user_id
        # Desafío consumido y contador TOTP no pueden reutilizarse.
        assert verify_login_challenge(
            engine=engine, cipher=cipher, challenge_token=challenge,
            code=totp_at(secret, int(login_now.timestamp())), now=login_now,
        ) is None

        recovery_challenge = issue_login_challenge(
            engine=engine, user_id=user_id, purpose="oauth", now=login_now,
        )
        assert verify_login_challenge(
            engine=engine, cipher=cipher, challenge_token=recovery_challenge,
            code=recovery_codes[0], now=login_now,
        ) == user_id
        replay_challenge = issue_login_challenge(
            engine=engine, user_id=user_id, now=login_now,
        )
        assert verify_login_challenge(
            engine=engine, cipher=cipher, challenge_token=replay_challenge,
            code=recovery_codes[0], now=now,
        ) is None

        expired = issue_login_challenge(
            engine=engine, user_id=user_id, now=now,
        )
        assert verify_login_challenge(
            engine=engine, cipher=cipher, challenge_token=expired,
            code=totp_at(secret, int(login_now.timestamp())),
            now=login_now + timedelta(minutes=6),
        ) is None

        with engine.connect() as conn:
            credential = conn.execute(text("""
                SELECT state,last_accepted_counter FROM user_mfa_credentials
                WHERE user_id=:user_id
            """), {"user_id": user_id}).one()
            used_recovery = conn.execute(text("""
                SELECT used_at FROM user_mfa_recovery_codes
                WHERE user_id=:user_id AND code_hash=:code_hash
            """), {"user_id": user_id, "code_hash": hash_recovery_code(recovery_codes[0])}).scalar_one()
        assert credential.state == "enabled"
        assert credential.last_accepted_counter >= 0
        assert used_recovery is not None
    finally:
        # La tabla de auditoría es append-only y las relaciones MFA usan RESTRICT.
        # PostgreSQL vive solo durante este job CI; no borrar ni alterar sus eventos.
        engine.dispose()
