"""Integración PostgreSQL del ciclo de códigos SSO landing -> Studio.

Fija el contrato de seguridad de un solo uso:
- authorize exige sesión y CSRF (probado a nivel de ruta por contrato HTTP);
- exchange consume el código atómicamente: el replay, el estado incorrecto, la
  expiración o el código ya consumido devuelven 401;
- la sesión creada en exchange funciona de inmediato (usuario autenticado).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

from fastapi import HTTPException  # noqa: E402

from api.auth import create_session  # noqa: E402
from api import sso_routes  # noqa: E402


def _user():
    user_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id, email, email_normalized, password_hash,
                               display_name, status, email_verified_at, terms_accepted_at)
            VALUES (:id, :email, :email, 'test-hash', 'SSO test', 'active', now(), now())
        """), {"id": user_id, "email": f"{user_id}@example.invalid"})
    return user_id


def _clean():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sso_codes"))


_clean()

ORIGIN = "https://studio.axyronatomic.com"


def current_user_exchange(token: str):
    from api.auth import current_user

    return current_user(token)


def test_authorize_then_exchange_creates_working_session():
    user_id = _user()
    code = sso_routes.authorize_sso_code(user_id=user_id, origin=ORIGIN)
    assert code["studio_url"].startswith(ORIGIN + "/sso/callback#code=")
    assert "?code=" not in code["studio_url"]

    token, csrf = sso_routes.exchange_sso_code(code=code["code"], state=code["state"])
    assert token and csrf

    from api.auth import current_user
    # La sesión creada en exchange autentica de inmediato.
    exchanged = current_user_exchange(token)
    assert exchanged["id"] == user_id


def test_exchange_replay_rejected():
    user_id = _user()
    code = sso_routes.authorize_sso_code(user_id=user_id, origin=ORIGIN)
    sso_routes.exchange_sso_code(code=code["code"], state=code["state"])
    with pytest.raises(HTTPException) as caught:
        sso_routes.exchange_sso_code(code=code["code"], state=code["state"])
    assert caught.value.status_code == 401


def test_exchange_wrong_state_rejected():
    user_id = _user()
    code = sso_routes.authorize_sso_code(user_id=user_id, origin=ORIGIN)
    with pytest.raises(HTTPException) as caught:
        sso_routes.exchange_sso_code(code=code["code"], state="x" * 43)
    assert caught.value.status_code == 401


def test_exchange_expired_code_rejected():
    from datetime import timedelta

    user_id = _user()
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    code = sso_routes.authorize_sso_code(user_id=user_id, origin=ORIGIN, now=past)
    with pytest.raises(HTTPException) as caught:
        sso_routes.exchange_sso_code(code=code["code"], state=code["state"])
    assert caught.value.status_code == 401


def test_exchange_unknown_code_rejected():
    with pytest.raises(HTTPException) as caught:
        sso_routes.exchange_sso_code(code="x" * 43, state="y" * 43)
    assert caught.value.status_code == 401


def test_exchange_creates_distinct_session_from_authorize_session():
    user_id = _user()
    landing_token, _ = create_session(user_id)
    code = sso_routes.authorize_sso_code(user_id=user_id, origin=ORIGIN)
    studio_token, _ = sso_routes.exchange_sso_code(code=code["code"], state=code["state"])
    assert landing_token != studio_token
    # La revocación de la sesión landing no invalida la del studio (sesiones independientes).
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE user_sessions SET revoked_at = now()
            WHERE token_hash = :digest
        """), {"digest": sso_routes._digest(landing_token)})


def test_authorize_requires_https_origin():
    user_id = _user()
    with pytest.raises(HTTPException) as caught:
        sso_routes.authorize_sso_code(user_id=user_id, origin="http://studio.axyronatomic.com")
    assert caught.value.status_code == 503


def test_exchange_non_ascii_state_is_rejected_without_crashing():
    """Una entrada no ASCII debe ser 401, no un UnicodeEncodeError/500."""
    user_id = _user()
    code = sso_routes.authorize_sso_code(user_id=user_id, origin=ORIGIN)
    with pytest.raises(HTTPException) as caught:
        sso_routes.exchange_sso_code(code=code["code"], state="ñ" * 43)
    assert caught.value.status_code == 401


def test_exchange_rejects_account_suspended_after_authorize():
    user_id = _user()
    code = sso_routes.authorize_sso_code(user_id=user_id, origin=ORIGIN)
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET status='disabled' WHERE id=:id"), {"id": user_id})
    with pytest.raises(HTTPException) as caught:
        sso_routes.exchange_sso_code(code=code["code"], state=code["state"])
    assert caught.value.status_code == 401
