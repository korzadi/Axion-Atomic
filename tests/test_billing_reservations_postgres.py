"""Integration tests for transactional credit reservations (PostgreSQL CI only)."""
import asyncio
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from api.billing_policy import InsufficientCredits
from api.billing_budget import InferenceBudget
from api.billing_execution import DuplicateExecution, execute_reserved_inference
from api.billing_reservations import (
    IdempotencyConflict,
    ReservationStateError,
    mark_reservation_unknown,
    reconcile_confirmed_no_execution,
    reserve_credits,
    reverse_settled_reservation,
    settle_reservation,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)


def _account(quota: int = 20):
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id, email, email_normalized, password_hash, display_name, status)
            VALUES (:id, :email, :email_normalized, 'test-hash-not-a-real-credential',
                    'Billing test', 'active')
        """), {
            "id": user_id,
            "email": f"{user_id}@example.invalid",
            "email_normalized": f"{user_id}@example.invalid",
        })
        conn.execute(text("""
            INSERT INTO projects (id, name) VALUES (:id, 'Billing integration test')
        """), {"id": project_id})
        conn.execute(text("""
            INSERT INTO billing_quota_periods
                (id, user_id, quota_kind, period_start, period_end, timezone_name,
                 limit_credits, policy_version)
            VALUES (CAST(:id AS UUID), :user_id, 'daily_free', :start, :end,
                    'UTC', :quota, 'test-v1')
        """), {
            "id": str(uuid.uuid4()), "user_id": user_id,
            "start": now - timedelta(minutes=1),
            "end": now + timedelta(days=1), "quota": quota,
        })
    return user_id, project_id


def _reserve(user_id, project_id, *, key, amount, request_id=None, digest=None, purchased_fallback_allowed=False, policy_version="test-v1"):
    return reserve_credits(
        engine=engine,
        user_id=user_id,
        project_id=project_id,
        request_id=request_id or str(uuid.uuid4()),
        idempotency_key=key,
        payload_sha256=digest or ("a" * 64),
        required_credits=amount,
        policy_version=policy_version,
        purchased_fallback_allowed=purchased_fallback_allowed,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


def test_reservation_is_idempotent_and_partial_settlement_releases_unused_quota():
    user_id, project_id = _account(quota=20)
    request_id = str(uuid.uuid4())
    first = _reserve(user_id, project_id, key="idem-partial", amount=8, request_id=request_id)
    repeated = _reserve(user_id, project_id, key="idem-partial", amount=8, request_id=request_id)
    assert repeated.idempotent is True
    assert repeated.reservation_id == first.reservation_id

    settled = settle_reservation(
        engine=engine, user_id=user_id, reservation_id=first.reservation_id,
        actual_credits=5,
    )
    assert settled.state == "settled"
    assert settled.charged_credits == 5
    repeated_settlement = settle_reservation(
        engine=engine, user_id=user_id, reservation_id=first.reservation_id,
        actual_credits=5,
    )
    assert repeated_settlement.idempotent is True
    assert repeated_settlement.charged_credits == 5

    with engine.connect() as conn:
        balances = conn.execute(text("""
            SELECT reserved_credits, consumed_credits
            FROM billing_quota_periods WHERE user_id=:user_id
        """), {"user_id": user_id}).one()
        entries = conn.execute(text("""
            SELECT event_type, count(*) AS n
            FROM billing_credit_ledger
            WHERE user_id=:user_id
            GROUP BY event_type
        """), {"user_id": user_id}).all()
    assert balances.reserved_credits == 0
    assert balances.consumed_credits == 5
    assert {row.event_type: row.n for row in entries} == {
        "reserve": 1, "consume": 1, "release": 1,
    }


def test_same_idempotency_key_rejects_changed_request_or_reservation_amount():
    user_id, project_id = _account(quota=30)
    request_id = str(uuid.uuid4())
    _reserve(user_id, project_id, key="idem-binding", amount=8, request_id=request_id)
    with pytest.raises(IdempotencyConflict):
        _reserve(user_id, project_id, key="idem-binding", amount=9, request_id=request_id)
    with pytest.raises(IdempotencyConflict):
        _reserve(user_id, project_id, key="idem-binding", amount=8, request_id=str(uuid.uuid4()))
    with pytest.raises(IdempotencyConflict):
        _reserve(user_id, project_id, key="idem-binding", amount=8,
                 request_id=request_id, policy_version="test-v2")
    other_project = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO projects (id, name) VALUES (:id, 'Other project')"),
                     {"id": other_project})
    with pytest.raises(IdempotencyConflict):
        _reserve(user_id, other_project, key="idem-binding", amount=8, request_id=request_id)


def test_same_idempotency_key_with_different_payload_is_rejected():
    user_id, project_id = _account(quota=20)
    _reserve(user_id, project_id, key="idem-conflict", amount=4, digest="b" * 64)
    with pytest.raises(IdempotencyConflict):
        _reserve(user_id, project_id, key="idem-conflict", amount=4, digest="c" * 64)


def test_concurrent_reservations_cannot_overspend_a_quota_period():
    user_id, project_id = _account(quota=10)

    def attempt(index):
        return _reserve(
            user_id, project_id, key=f"concurrent-{index}", amount=7,
        )

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, index) for index in range(2)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except InsufficientCredits:
                outcomes.append("insufficient")

    assert sum(1 for item in outcomes if item != "insufficient") == 1
    assert outcomes.count("insufficient") == 1
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT reserved_credits, consumed_credits, limit_credits
            FROM billing_quota_periods WHERE user_id=:user_id
        """), {"user_id": user_id}).one()
    assert row.reserved_credits == 7
    assert row.reserved_credits + row.consumed_credits <= row.limit_credits



def test_purchased_lots_reserve_and_settle_in_fefo_order():
    user_id, project_id = _account(quota=0)
    now = datetime.now(timezone.utc)
    earlier_id, later_id = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        for lot_id, expiry, reference in (
            (earlier_id, now + timedelta(days=2), "fefo-earlier"),
            (later_id, now + timedelta(days=5), "fefo-later"),
        ):
            conn.execute(text("""
                INSERT INTO billing_credit_lots
                    (id, user_id, source, source_reference, granted_credits,
                     available_credits, expires_at)
                VALUES (CAST(:id AS UUID), :user_id, 'purchased', :reference,
                        5, 5, :expiry)
            """), {
                "id": lot_id, "user_id": user_id,
                "reference": reference, "expiry": expiry,
            })

    reservation = _reserve(user_id, project_id, key="fefo-reserve", amount=8, purchased_fallback_allowed=True)
    with engine.connect() as conn:
        reserved = conn.execute(text("""
            SELECT credit_lot_id, allocated_credits
            FROM billing_reservation_allocations
            WHERE reservation_id=CAST(:id AS UUID)
            ORDER BY created_at, id
        """), {"id": reservation.reservation_id}).all()
    assert {str(row.credit_lot_id): row.allocated_credits for row in reserved} == {
        earlier_id: 5, later_id: 3,
    }

    settle_reservation(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
        actual_credits=4,
    )
    with engine.connect() as conn:
        balances = conn.execute(text("""
            SELECT id, available_credits, reserved_credits, consumed_credits
            FROM billing_credit_lots WHERE user_id=:user_id
        """), {"user_id": user_id}).all()
    result = {
        str(row.id): (row.available_credits, row.reserved_credits, row.consumed_credits)
        for row in balances
    }
    assert result[earlier_id] == (1, 0, 4)
    assert result[later_id] == (5, 0, 0)


def test_usage_above_reservation_enters_review_without_extra_debit():
    user_id, project_id = _account(quota=10)
    reservation = _reserve(user_id, project_id, key="over-reservation", amount=5)
    result = settle_reservation(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
        actual_credits=6,
    )
    assert result.state == "review"
    assert result.charged_credits is None
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT q.reserved_credits, q.consumed_credits, r.state
            FROM billing_quota_periods q
            JOIN billing_usage_reservations r ON r.user_id=q.user_id
            WHERE q.user_id=:user_id
        """), {"user_id": user_id}).one()
    assert row.state == "review"
    assert row.reserved_credits == 5
    assert row.consumed_credits == 0



def test_purchased_credits_are_not_used_without_plan_permission():
    user_id, project_id = _account(quota=0)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO billing_credit_lots
                (id, user_id, source, source_reference, granted_credits, available_credits)
            VALUES (CAST(:id AS UUID), :user_id, 'purchased', 'fallback-disabled',
                    10, 10)
        """), {"id": str(uuid.uuid4()), "user_id": user_id})

    with pytest.raises(InsufficientCredits):
        _reserve(user_id, project_id, key="fallback-disabled", amount=5)

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT available_credits, reserved_credits
            FROM billing_credit_lots WHERE user_id=:user_id
        """), {"user_id": user_id}).one()
    assert row.available_credits == 10
    assert row.reserved_credits == 0



def test_unknown_provider_result_keeps_credits_reserved():
    user_id, project_id = _account(quota=10)
    reservation = _reserve(user_id, project_id, key="unknown-result", amount=6)
    mark_reservation_unknown(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
    )
    # Repetir la notificación del proveedor no debe liberar ni alterar el saldo.
    mark_reservation_unknown(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
    )
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT q.reserved_credits, q.consumed_credits, r.state
            FROM billing_quota_periods q
            JOIN billing_usage_reservations r ON r.user_id=q.user_id
            WHERE q.user_id=:user_id
        """), {"user_id": user_id}).one()
    assert row.state == "unknown"
    assert row.reserved_credits == 6
    assert row.consumed_credits == 0



def test_unknown_reservation_requires_audited_confirmation_before_release():
    user_id, project_id = _account(quota=10)
    reservation = _reserve(user_id, project_id, key="reconcile-no-execution", amount=6)
    mark_reservation_unknown(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
    )

    result = reconcile_confirmed_no_execution(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
        actor_user_id=user_id, reason="Proveedor confirmó por escrito que no ejecutó la solicitud.",
        idempotency_key="admin-reconcile-001",
    )
    assert result.state == "released"
    repeated = reconcile_confirmed_no_execution(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
        actor_user_id=user_id, reason="Proveedor confirmó por escrito que no ejecutó la solicitud.",
        idempotency_key="admin-reconcile-001",
    )
    assert repeated.idempotent is True

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT q.reserved_credits, q.consumed_credits, r.state
            FROM billing_quota_periods q
            JOIN billing_usage_reservations r ON r.user_id=q.user_id
            WHERE q.user_id=:user_id
        """), {"user_id": user_id}).one()
        audit_count = conn.execute(text("""
            SELECT count(*) FROM billing_reservation_reconciliations
            WHERE reservation_id=CAST(:id AS UUID)
        """), {"id": reservation.reservation_id}).scalar_one()
        release_count = conn.execute(text("""
            SELECT count(*) FROM billing_credit_ledger
            WHERE reservation_id=CAST(:id AS UUID) AND event_type='release'
        """), {"id": reservation.reservation_id}).scalar_one()
    assert row.state == "released"
    assert row.reserved_credits == 0
    assert row.consumed_credits == 0
    assert audit_count == 1
    assert release_count == 1


def test_held_reservation_cannot_be_released_by_reconciliation():
    user_id, project_id = _account(quota=10)
    reservation = _reserve(user_id, project_id, key="reconcile-held", amount=4)
    from api.billing_reservations import ReservationStateError
    with pytest.raises(ReservationStateError):
        reconcile_confirmed_no_execution(
            engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
            actor_user_id=user_id, reason="No ejecución confirmada por proveedor.",
            idempotency_key="admin-reconcile-held",
        )


def _execution_budget():
    return InferenceBudget(
        policy_version="atomic-code-budget-v1",
        runtime_model="atomic-code:16k-8k",
        tokenizer_contract="qwen2_byte_fallback",
        input_tokens_upper_bound=100,
        output_tokens_upper_bound=50,
        input_weight=1,
        output_weight=1,
        reserved_credits=150,
        context_window=16384,
    )


def _execute_reserved(user_id, project_id, key, inference_call, request_id=None):
    return asyncio.run(execute_reserved_inference(
        engine=engine, user_id=user_id, project_id=project_id,
        request_id=request_id or str(uuid.uuid4()), idempotency_key=key,
        payload_sha256="d" * 64, budget=_execution_budget(),
        expected_runtime_model="atomic-code:16k-8k",
        inference_call=inference_call,
        reservation_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    ))


def test_execution_orchestrator_reserves_then_infers_and_settles_postgres():
    user_id, project_id = _account(quota=200)
    calls = []

    async def inference():
        calls.append("inference")
        from types import SimpleNamespace
        return SimpleNamespace(
            requested_model="atomic-code:16k-8k",
            returned_model="atomic-code:16k-8k",
            done=True, prompt_eval_count=12, eval_count=8,
            usage_source="ollama_response",
        )

    result = _execute_reserved(user_id, project_id, "orchestrator-success", inference)
    assert calls == ["inference"]
    assert result.reservation.state == "held"
    assert result.settlement.state == "settled"
    assert result.settlement.charged_credits == 20
    with engine.connect() as conn:
        quota = conn.execute(text("""
            SELECT reserved_credits, consumed_credits
            FROM billing_quota_periods WHERE user_id=:user_id
        """), {"user_id": user_id}).one()
    assert quota.reserved_credits == 0
    assert quota.consumed_credits == 20


def test_execution_orchestrator_retry_does_not_repeat_provider_call():
    user_id, project_id = _account(quota=200)
    from types import SimpleNamespace

    async def inference():
        return SimpleNamespace(
            requested_model="atomic-code:16k-8k",
            returned_model="atomic-code:16k-8k",
            done=True, prompt_eval_count=12, eval_count=8,
            usage_source="ollama_response",
        )

    request_id = str(uuid.uuid4())
    first = _execute_reserved(user_id, project_id, "orchestrator-idempotent", inference, request_id=request_id)
    assert first.settlement.state == "settled"
    repeated_calls = []

    async def must_not_run():
        repeated_calls.append(True)

    with pytest.raises(DuplicateExecution):
        _execute_reserved(user_id, project_id, "orchestrator-idempotent", must_not_run, request_id=request_id)
    assert repeated_calls == []


def test_execution_orchestrator_timeout_keeps_postgres_reservation_unknown():
    user_id, project_id = _account(quota=200)

    async def timeout():
        raise TimeoutError("simulated provider timeout")

    with pytest.raises(TimeoutError):
        _execute_reserved(user_id, project_id, "orchestrator-timeout", timeout)
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT q.reserved_credits, q.consumed_credits, r.state
            FROM billing_quota_periods q
            JOIN billing_usage_reservations r ON r.user_id=q.user_id
            WHERE q.user_id=:user_id
        """), {"user_id": user_id}).one()
    assert row.state == "unknown"
    assert row.reserved_credits == 150
    assert row.consumed_credits == 0


def test_concurrent_settlement_is_idempotent_and_never_double_charges():
    user_id, project_id = _account(quota=30)
    reservation = _reserve(
        user_id, project_id, key="concurrent-settlement", amount=12,
    )

    def settle():
        return settle_reservation(
            engine=engine, user_id=user_id,
            reservation_id=reservation.reservation_id, actual_credits=7,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=10) for future in [
            pool.submit(settle), pool.submit(settle),
        ]]

    assert all(result.state == "settled" for result in results)
    assert sorted(result.idempotent for result in results) == [False, True]
    assert all(result.charged_credits == 7 for result in results)

    with engine.connect() as conn:
        balance = conn.execute(text("""
            SELECT reserved_credits, consumed_credits
            FROM billing_quota_periods WHERE user_id=:user_id
        """), {"user_id": user_id}).one()
        ledger = conn.execute(text("""
            SELECT event_type, count(*) AS entries, coalesce(sum(consumed_delta), 0) AS credits
            FROM billing_credit_ledger
            WHERE user_id=:user_id
            GROUP BY event_type
        """), {"user_id": user_id}).all()

    assert balance.reserved_credits == 0
    assert balance.consumed_credits == 7
    by_type = {row.event_type: (row.entries, row.credits) for row in ledger}
    assert by_type["reserve"] == (1, 0)
    assert by_type["consume"] == (1, 7)
    assert by_type["release"] == (1, 0)



def test_reversal_restores_consumed_quota_once_and_is_idempotent():
    user_id, project_id = _account(quota=20)
    reservation = _reserve(user_id, project_id, key="reversal-quota", amount=8)
    settle_reservation(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
        actual_credits=5,
    )
    first = reverse_settled_reservation(
        engine=engine, reservation_id=reservation.reservation_id,
        actor_user_id=user_id, reason="Reversión administrativa verificada",
        idempotency_key="reversal-quota-1",
    )
    repeated = reverse_settled_reservation(
        engine=engine, reservation_id=reservation.reservation_id,
        actor_user_id=user_id, reason="Reversión administrativa verificada",
        idempotency_key="reversal-quota-1",
    )
    assert first.reversed_credits == 5
    assert first.idempotent is False
    assert repeated.idempotent is True
    with pytest.raises(IdempotencyConflict):
        reverse_settled_reservation(
            engine=engine, reservation_id=reservation.reservation_id,
            actor_user_id=user_id, reason="Reversión administrativa verificada",
            idempotency_key="reversal-quota-2",
        )

    with engine.connect() as conn:
        balance = conn.execute(text("""
            SELECT reserved_credits, consumed_credits
            FROM billing_quota_periods WHERE user_id=:user_id
        """), {"user_id": user_id}).one()
        reversals = conn.execute(text("""
            SELECT available_delta, reserved_delta, consumed_delta, related_entry_id
            FROM billing_credit_ledger
            WHERE user_id=:user_id AND event_type='reversal'
        """), {"user_id": user_id}).all()
    assert balance.reserved_credits == 0
    assert balance.consumed_credits == 0
    assert len(reversals) == 1
    assert reversals[0].available_delta == 0
    assert reversals[0].reserved_delta == 0
    assert reversals[0].consumed_delta == -5
    assert reversals[0].related_entry_id is not None


def test_reversal_returns_purchased_credits_to_the_same_lot():
    user_id, project_id = _account(quota=0)
    now = datetime.now(timezone.utc)
    lot_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO billing_credit_lots
                (id, user_id, source, source_reference, granted_credits,
                 available_credits, expires_at)
            VALUES (CAST(:id AS UUID), :user_id, 'purchased', 'reversal-lot',
                    10, 10, :expiry)
        """), {"id": lot_id, "user_id": user_id, "expiry": now + timedelta(days=3)})
    reservation = _reserve(
        user_id, project_id, key="reversal-lot-reserve", amount=8,
        purchased_fallback_allowed=True,
    )
    settle_reservation(
        engine=engine, user_id=user_id, reservation_id=reservation.reservation_id,
        actual_credits=6,
    )
    result = reverse_settled_reservation(
        engine=engine, reservation_id=reservation.reservation_id,
        actor_user_id=user_id, reason="Reversión administrativa verificada",
        idempotency_key="reversal-lot-1",
    )
    assert result.reversed_credits == 6
    with engine.connect() as conn:
        lot = conn.execute(text("""
            SELECT available_credits, reserved_credits, consumed_credits
            FROM billing_credit_lots WHERE id=CAST(:id AS UUID)
        """), {"id": lot_id}).one()
        reversal = conn.execute(text("""
            SELECT available_delta, reserved_delta, consumed_delta
            FROM billing_credit_ledger
            WHERE user_id=:user_id AND event_type='reversal'
        """), {"user_id": user_id}).one()
    assert (lot.available_credits, lot.reserved_credits, lot.consumed_credits) == (10, 0, 0)
    assert (reversal.available_delta, reversal.reserved_delta, reversal.consumed_delta) == (6, 0, -6)


def test_reversal_rejects_reservations_without_settled_consumption():
    user_id, project_id = _account(quota=20)
    held = _reserve(user_id, project_id, key="reversal-held", amount=4)
    with pytest.raises(ReservationStateError):
        reverse_settled_reservation(
            engine=engine, reservation_id=held.reservation_id,
            actor_user_id=user_id, reason="Reversión administrativa verificada",
            idempotency_key="reversal-held-1",
        )
    settled_without_usage = _reserve(user_id, project_id, key="reversal-zero", amount=4)
    settle_reservation(
        engine=engine, user_id=user_id,
        reservation_id=settled_without_usage.reservation_id, actual_credits=0,
    )
    with pytest.raises(ReservationStateError):
        reverse_settled_reservation(
            engine=engine, reservation_id=settled_without_usage.reservation_id,
            actor_user_id=user_id, reason="Reversión administrativa verificada",
            idempotency_key="reversal-zero-1",
        )
