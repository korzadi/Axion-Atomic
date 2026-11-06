"""Durable billing recovery integration tests (PostgreSQL CI only)."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

from api.billing_budget import InferenceBudget
from api.billing_execution_durable import execute_durable_reserved_inference
from api.billing_result_crypto import AesGcmResultCipher
from api.billing_recovery import recover_completed_billing_executions, _claim_attempt
from api.billing_execution_envelope import (
    serialize_billing_execution_result,
    deserialize_billing_execution_result,
)


class TestKeyProvider:
    def active_key(self):
        return "integration-v1", b"K" * 32

    def get_key(self, key_id):
        assert key_id == "integration-v1"
        return b"K" * 32


def _account():
    user_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id, email, email_normalized, password_hash, display_name, status)
            VALUES (:id, :email, :email, 'integration-test-hash', 'Durable billing test', 'active')
        """), {"id": user_id, "email": f"{user_id}@example.invalid"})
        conn.execute(text("INSERT INTO projects (id, name) VALUES (:id, 'Durable billing test')"),
                     {"id": project_id})
        conn.execute(text("""
            INSERT INTO billing_quota_periods
              (id,user_id,quota_kind,period_start,period_end,timezone_name,limit_credits,policy_version)
            VALUES (CAST(:id AS UUID),:user_id,'daily_free',:start,:end,'UTC',200,'atomic-code-budget-v1')
        """), {"id": str(uuid.uuid4()), "user_id": user_id,
               "start": now-timedelta(minutes=1), "end": now+timedelta(days=1)})
    return user_id, project_id


def _budget():
    return InferenceBudget(
        policy_version="atomic-code-budget-v1", runtime_model="atomic-code:16k-8k",
        tokenizer_contract="qwen2_byte_fallback", input_tokens_upper_bound=100,
        output_tokens_upper_bound=50, input_weight=1, output_weight=1,
        reserved_credits=150, context_window=16384,
    )


def _serialize(result):
    return serialize_billing_execution_result(
        result,
        expected_model="atomic-code:16k-8k",
        policy_version="atomic-code-budget-v1",
        input_weight=1,
        output_weight=1,
    )


def _deserialize(payload):
    return deserialize_billing_execution_result(payload)


def _execute(user_id, project_id, request_id, inference):
    return asyncio.run(execute_durable_reserved_inference(
        engine=engine, user_id=user_id, project_id=project_id,
        request_id=request_id, idempotency_key="durable-recovery-key",
        payload_sha256="f"*64, budget=_budget(),
        expected_runtime_model="atomic-code:16k-8k",
        inference_call=inference,
        reservation_expires_at=datetime.now(timezone.utc)+timedelta(minutes=5),
        cipher=AesGcmResultCipher(TestKeyProvider()),
        serialize_result=_serialize, deserialize_result=_deserialize,
    ))


def test_persisted_result_recovers_after_settlement_failure_without_second_inference():
    user_id, project_id = _account()
    request_id = str(uuid.uuid4())
    calls = []

    async def inference():
        calls.append("called")
        return SimpleNamespace(
            requested_model="atomic-code:16k-8k",
            returned_model="atomic-code:16k-8k",
            done=True, usage_source="ollama_response",
            prompt_eval_count=12, eval_count=8,
            content="durable-result-secret-marker",
        )

    with patch(
        "api.billing_execution_durable.settle_reservation",
        side_effect=RuntimeError("simulated database settlement outage"),
    ):
        with pytest.raises(RuntimeError, match="settlement outage"):
            _execute(user_id, project_id, request_id, inference)

    with engine.connect() as conn:
        execution = conn.execute(text("""
            SELECT e.state, e.result_ciphertext, e.result_nonce, e.result_key_id,
                   r.state AS reservation_state
            FROM billing_inference_executions e
            JOIN billing_usage_reservations r ON r.id=e.reservation_id
            WHERE e.user_id=:user_id
        """), {"user_id": user_id}).mappings().one()
    assert execution["state"] == "completed"
    assert execution["reservation_state"] == "held"
    assert b"durable-result-secret-marker" not in bytes(execution["result_ciphertext"])

    recovered = _execute(user_id, project_id, request_id, inference)
    assert recovered.recovered is True
    assert recovered.inference.content == "durable-result-secret-marker"
    assert recovered.settlement.state == "settled"
    assert calls == ["called"]

    with engine.connect() as conn:
        balances = conn.execute(text("""
            SELECT reserved_credits, consumed_credits
            FROM billing_quota_periods WHERE user_id=:user_id
        """), {"user_id": user_id}).one()
        states = conn.execute(text("""
            SELECT r.state, e.state AS execution_state
            FROM billing_usage_reservations r
            JOIN billing_inference_executions e ON e.reservation_id=r.id
            WHERE r.user_id=:user_id
        """), {"user_id": user_id}).one()
    assert balances.reserved_credits == 0
    assert balances.consumed_credits == 20
    assert states.state == "settled"
    assert states.execution_state == "completed"



def test_recovery_worker_settles_completed_execution_without_second_inference():
    user_id, project_id = _account()
    request_id = str(uuid.uuid4())
    calls = []

    async def inference():
        calls.append("called")
        return SimpleNamespace(
            requested_model="atomic-code:16k-8k",
            returned_model="atomic-code:16k-8k",
            done=True, usage_source="ollama_response",
            prompt_eval_count=12, eval_count=8,
            content="recovery-worker-secret-marker",
        )

    with patch(
        "api.billing_execution_durable.settle_reservation",
        side_effect=RuntimeError("simulated settlement outage"),
    ):
        with pytest.raises(RuntimeError, match="settlement outage"):
            _execute(user_id, project_id, request_id, inference)

    with engine.connect() as conn:
        target_reservation_id = conn.execute(text("""
            SELECT id FROM billing_usage_reservations WHERE user_id=:user_id
        """), {"user_id": user_id}).scalar_one()

    cipher = AesGcmResultCipher(TestKeyProvider())
    batch = recover_completed_billing_executions(
        engine=engine, cipher=cipher, limit=10,
        reservation_id=str(target_reservation_id),
    )
    assert batch.examined == 1
    assert batch.settled == 1
    assert batch.failed == 0
    assert calls == ["called"]

    repeated = recover_completed_billing_executions(
        engine=engine, cipher=cipher, limit=10,
        reservation_id=str(target_reservation_id),
    )
    assert repeated.examined == 0
    assert repeated.settled == 0

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT r.state AS reservation_state, q.reserved_credits,
                   q.consumed_credits, e.recovery_attempts,
                   e.recovery_next_attempt_at, e.recovery_settled_at
            FROM billing_usage_reservations r
            JOIN billing_quota_periods q ON q.user_id=r.user_id
            JOIN billing_inference_executions e ON e.reservation_id=r.id
            WHERE r.user_id=:user_id
        """), {"user_id": user_id}).mappings().one()
    assert row["reservation_state"] == "settled"
    assert row["reserved_credits"] == 0
    assert row["consumed_credits"] == 20
    assert row["recovery_attempts"] == 1
    assert row["recovery_next_attempt_at"] is None
    assert row["recovery_settled_at"] is not None



def test_recovery_claim_is_exclusive_across_concurrent_workers():
    user_id, project_id = _account()
    request_id = str(uuid.uuid4())

    async def inference():
        return SimpleNamespace(
            requested_model="atomic-code:16k-8k",
            returned_model="atomic-code:16k-8k",
            done=True, usage_source="ollama_response",
            prompt_eval_count=12, eval_count=8, content="concurrency-marker",
        )

    with patch(
        "api.billing_execution_durable.settle_reservation",
        side_effect=RuntimeError("simulated settlement outage"),
    ):
        with pytest.raises(RuntimeError, match="settlement outage"):
            _execute(user_id, project_id, request_id, inference)

    with engine.connect() as conn:
        execution_id = conn.execute(text("""
            SELECT id FROM billing_inference_executions WHERE user_id=:user_id
        """), {"user_id": user_id}).scalar_one()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_claim_attempt, engine, str(execution_id)),
            pool.submit(_claim_attempt, engine, str(execution_id)),
        ]
        claims = [future.result(timeout=10) for future in futures]

    assert sorted(value for value in claims if value is not None) == [1]
    assert claims.count(None) == 1


def test_recovery_decrypt_failure_sets_backoff_and_is_not_retried_immediately():
    user_id, project_id = _account()
    request_id = str(uuid.uuid4())

    async def inference():
        return SimpleNamespace(
            requested_model="atomic-code:16k-8k",
            returned_model="atomic-code:16k-8k",
            done=True, usage_source="ollama_response",
            prompt_eval_count=12, eval_count=8, content="backoff-marker",
        )

    with patch(
        "api.billing_execution_durable.settle_reservation",
        side_effect=RuntimeError("simulated settlement outage"),
    ):
        with pytest.raises(RuntimeError, match="settlement outage"):
            _execute(user_id, project_id, request_id, inference)

    with engine.connect() as conn:
        target_reservation_id = conn.execute(text("""
            SELECT id FROM billing_usage_reservations WHERE user_id=:user_id
        """), {"user_id": user_id}).scalar_one()

    class BrokenCipher:
        def decrypt(self, *args, **kwargs):
            raise ValueError("invalid test ciphertext")

    batch = recover_completed_billing_executions(
        engine=engine, cipher=BrokenCipher(), limit=10,
        reservation_id=str(target_reservation_id),
    )
    assert batch.examined == 1
    assert batch.failed == 1

    with engine.connect() as conn:
        state = conn.execute(text("""
            SELECT recovery_attempts, recovery_next_attempt_at,
                   recovery_last_error_code
            FROM billing_inference_executions WHERE user_id=:user_id
        """), {"user_id": user_id}).mappings().one()

    assert state["recovery_attempts"] == 1
    assert state["recovery_next_attempt_at"] is not None
    assert state["recovery_last_error_code"] == "ValueError"

    repeated = recover_completed_billing_executions(
        engine=engine, cipher=BrokenCipher(), limit=10,
        reservation_id=str(target_reservation_id),
    )
    assert repeated.examined == 0
    assert repeated.failed == 0
