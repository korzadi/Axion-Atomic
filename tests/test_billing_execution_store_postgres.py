import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

from api.billing_execution_store import (
    ExecutionAlreadyClaimed,
    ExecutionStoreError,
    claim_execution,
    load_encrypted_result,
    mark_execution_unknown,
    persist_encrypted_result,
)
from api.billing_reservations import mark_reservation_unknown, reserve_credits


def _reservation(engine):
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id, email, email_normalized, password_hash, display_name, status)
            VALUES (:id, :email, :email, 'test-hash', 'Execution test', 'active')
        """), {"id": user_id, "email": f"{user_id}@example.invalid"})
        conn.execute(text("INSERT INTO projects (id, name) VALUES (:id, 'Execution test')"),
                     {"id": project_id})
        conn.execute(text("""
            INSERT INTO billing_quota_periods
              (id,user_id,quota_kind,period_start,period_end,timezone_name,limit_credits,policy_version)
            VALUES (CAST(:id AS UUID),:user_id,'daily_free',:start,:end,'UTC',100,'test-v1')
        """), {"id": str(uuid.uuid4()), "user_id": user_id,
               "start": now-timedelta(minutes=1), "end": now+timedelta(days=1)})
    reservation = reserve_credits(
        engine=engine, user_id=user_id, project_id=project_id,
        request_id=str(uuid.uuid4()), idempotency_key="execution-store-test",
        payload_sha256="e"*64, required_credits=20, policy_version="test-v1",
        expires_at=now+timedelta(minutes=5),
    )
    return user_id, reservation.reservation_id


def test_execution_claim_is_unique_and_completed_ciphertext_is_recoverable():
    user_id, reservation_id = _reservation(engine)
    first = claim_execution(engine=engine, user_id=user_id, reservation_id=reservation_id)
    assert first.claimed is True
    repeated = claim_execution(engine=engine, user_id=user_id, reservation_id=reservation_id)
    assert repeated.claimed is False
    assert repeated.execution_id == first.execution_id
    assert repeated.state == "started"

    saved = persist_encrypted_result(
        engine=engine, user_id=user_id, execution_id=first.execution_id,
        ciphertext=b"ciphertext-not-plaintext", nonce=b"unique-nonce", key_id="test-key-v1",
    )
    loaded = load_encrypted_result(
        engine=engine, user_id=user_id, reservation_id=reservation_id,
    )
    assert loaded == saved
    with pytest.raises(ExecutionAlreadyClaimed):
        persist_encrypted_result(
            engine=engine, user_id=user_id, execution_id=first.execution_id,
            ciphertext=b"second-ciphertext", nonce=b"0123456789ab", key_id="test-key-v1",
        )



def test_concurrent_execution_claims_grant_exactly_one_inference_right():
    from concurrent.futures import ThreadPoolExecutor

    user_id, reservation_id = _reservation(engine)

    def claim():
        return claim_execution(
            engine=engine, user_id=user_id, reservation_id=reservation_id,
        )

    # Distintas conexiones compiten por la misma reserva real de PostgreSQL.
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: claim(), range(8)))

    assert sum(1 for item in claims if item.claimed) == 1
    assert len({item.execution_id for item in claims}) == 1
    assert {item.state for item in claims} == {"started"}

def test_started_execution_can_be_marked_unknown_and_never_reclaimed():
    user_id, reservation_id = _reservation(engine)
    first = claim_execution(engine=engine, user_id=user_id, reservation_id=reservation_id)
    mark_execution_unknown(engine=engine, user_id=user_id, execution_id=first.execution_id)
    repeated = claim_execution(engine=engine, user_id=user_id, reservation_id=reservation_id)
    assert repeated.claimed is False
    assert repeated.state == "unknown"
    assert load_encrypted_result(engine=engine, user_id=user_id, reservation_id=reservation_id) is None


def test_unknown_reservation_cannot_claim_first_execution():
    user_id, reservation_id = _reservation(engine)
    mark_reservation_unknown(engine=engine, user_id=user_id, reservation_id=reservation_id)
    with pytest.raises(ExecutionStoreError, match="held"):
        claim_execution(engine=engine, user_id=user_id, reservation_id=reservation_id)



@pytest.mark.parametrize(
    ("ciphertext", "nonce"),
    [
        (b"", b"0123456789ab"),
        (b"too-short", b"0123456789ab"),
        (b"valid-auth-tag-length", b"short"),
        (b"valid-auth-tag-length", b"0123456789abc"),
    ],
)
def test_malformed_aes_gcm_result_is_rejected_before_marking_execution_completed(ciphertext, nonce):
    user_id, reservation_id = _reservation(engine)
    claim = claim_execution(engine=engine, user_id=user_id, reservation_id=reservation_id)

    with pytest.raises(ValueError):
        persist_encrypted_result(
            engine=engine,
            user_id=user_id,
            execution_id=claim.execution_id,
            ciphertext=ciphertext,
            nonce=nonce,
            key_id="test-key-v1",
        )

    with engine.connect() as conn:
        state = conn.execute(text("""
            SELECT state FROM billing_inference_executions
            WHERE id=CAST(:id AS UUID)
        """), {"id": claim.execution_id}).scalar_one()
    assert state == "started"
    assert load_encrypted_result(
        engine=engine, user_id=user_id, reservation_id=reservation_id,
    ) is None
