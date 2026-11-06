"""Integration tests for transactional credit reservations (PostgreSQL CI only)."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from api.billing_policy import InsufficientCredits
from api.billing_reservations import (
    IdempotencyConflict,
    reserve_credits,
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


def _reserve(user_id, project_id, *, key, amount, request_id=None, digest=None):
    return reserve_credits(
        engine=engine,
        user_id=user_id,
        project_id=project_id,
        request_id=request_id or str(uuid.uuid4()),
        idempotency_key=key,
        payload_sha256=digest or ("a" * 64),
        required_credits=amount,
        policy_version="test-v1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


def test_reservation_is_idempotent_and_partial_settlement_releases_unused_quota():
    user_id, project_id = _account(quota=20)
    first = _reserve(user_id, project_id, key="idem-partial", amount=8)
    repeated = _reserve(user_id, project_id, key="idem-partial", amount=8)
    assert repeated.idempotent is True
    assert repeated.reservation_id == first.reservation_id

    settled = settle_reservation(
        engine=engine, user_id=user_id, reservation_id=first.reservation_id,
        actual_credits=5,
    )
    assert settled.state == "settled"
    assert settled.charged_credits == 5

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

    reservation = _reserve(user_id, project_id, key="fefo-reserve", amount=8)
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
