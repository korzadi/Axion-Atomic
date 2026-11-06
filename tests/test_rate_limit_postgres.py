"""Pruebas PostgreSQL del rate limiter distribuido."""
import os
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
from api.rate_limit import consume_rate_limit, rate_limit_key, prune_expired_rate_limits


def test_limit_allows_only_configured_number_of_hits():
    key = rate_limit_key("auth:login", "198.51.100.12")
    now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    decisions = [consume_rate_limit(engine=engine, bucket_key=key, limit=3,
                  window=timedelta(minutes=1), now=now) for _ in range(4)]
    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert decisions[-1].retry_after_seconds > 0


def test_fixed_window_resets_at_boundary():
    key = rate_limit_key("auth:register", "203.0.113.9")
    first = datetime(2026, 11, 6, 12, 0, 59, tzinfo=timezone.utc)
    next_window = datetime(2026, 11, 6, 12, 1, 0, tzinfo=timezone.utc)
    assert consume_rate_limit(engine=engine, bucket_key=key, limit=1,
        window=timedelta(minutes=1), now=first).allowed
    assert consume_rate_limit(engine=engine, bucket_key=key, limit=1,
        window=timedelta(minutes=1), now=next_window).allowed


def test_bucket_does_not_store_subject_in_clear():
    subject = "private-user@example.invalid"
    key = rate_limit_key("auth:reset", subject)
    assert subject not in key
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_rate_limit_buckets WHERE bucket_key=:key"), {"key": key})
    decision = consume_rate_limit(engine=engine, bucket_key=key, limit=1,
        window=timedelta(minutes=5))
    assert decision.allowed


def test_expired_bucket_cleanup_is_bounded():
    key = rate_limit_key("auth:cleanup", "test-subject")
    now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_rate_limit_buckets(bucket_key,window_start,hit_count,expires_at)
            VALUES (:key,:start,1,:expiry)
            ON CONFLICT(bucket_key,window_start) DO UPDATE SET expires_at=:expiry
        """), {"key": key, "start": now-timedelta(minutes=2), "expiry": now-timedelta(minutes=1)})
    assert prune_expired_rate_limits(engine=engine, now=now, batch_size=1) >= 1
