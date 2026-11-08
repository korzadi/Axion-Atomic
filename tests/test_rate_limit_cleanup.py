"""Regresiones portables para la limpieza y privacidad del rate limiter."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, text

from api.rate_limit import prune_expired_rate_limits, rate_limit_key


@pytest.fixture
def rate_limit_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    metadata = MetaData()
    Table(
        "auth_rate_limit_buckets",
        metadata,
        Column("bucket_key", String(64), primary_key=True),
        Column("window_start", DateTime(timezone=True), primary_key=True),
        Column("hit_count", Integer, nullable=False),
        Column("expires_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _insert_bucket(engine, key, start, expires):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO auth_rate_limit_buckets
                    (bucket_key, window_start, hit_count, expires_at)
                VALUES (:key, :start, 1, :expires)
            """),
            {"key": key, "start": start, "expires": expires},
        )


def test_rate_limit_key_is_stable_and_does_not_expose_subject():
    subject = "private-user@example.invalid"
    first = rate_limit_key("auth:reset", subject)
    second = rate_limit_key("auth:reset", subject)

    assert first == second
    assert len(first) == 64
    assert subject not in first
    assert first != rate_limit_key("auth:login", subject)


@pytest.mark.parametrize("namespace", ["", "Auth", "auth reset", "auth/../reset", "x" * 81, None])
def test_rate_limit_key_rejects_invalid_namespace(namespace):
    with pytest.raises(ValueError, match="namespace"):
        rate_limit_key(namespace, "opaque-subject")


@pytest.mark.parametrize("subject", ["", "x" * 513, None, 42])
def test_rate_limit_key_rejects_invalid_subject(subject):
    with pytest.raises(ValueError, match="subject"):
        rate_limit_key("auth:login", subject)


def test_cleanup_deletes_only_expired_buckets_and_respects_batch_limit(rate_limit_engine):
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    expired = [
        (rate_limit_key("auth:cleanup", f"expired-{index}"), now - timedelta(minutes=index + 2))
        for index in range(3)
    ]
    future_key = rate_limit_key("auth:cleanup", "still-active")
    for key, expiry in expired:
        _insert_bucket(rate_limit_engine, key, expiry - timedelta(minutes=1), expiry)
    _insert_bucket(rate_limit_engine, future_key, now, now + timedelta(minutes=5))

    first = prune_expired_rate_limits(engine=rate_limit_engine, now=now, batch_size=2)
    second = prune_expired_rate_limits(engine=rate_limit_engine, now=now, batch_size=2)

    assert first == 2
    assert second == 1
    with rate_limit_engine.connect() as conn:
        remaining = conn.execute(
            text("SELECT bucket_key FROM auth_rate_limit_buckets")
        ).scalars().all()
    assert remaining == [future_key]


def test_cleanup_treats_expiration_equal_to_now_as_expired(rate_limit_engine):
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    boundary_key = rate_limit_key("auth:cleanup", "boundary")
    future_key = rate_limit_key("auth:cleanup", "one-microsecond-future")
    _insert_bucket(rate_limit_engine, boundary_key, now - timedelta(minutes=1), now)
    _insert_bucket(
        rate_limit_engine, future_key, now,
        now + timedelta(microseconds=1),
    )

    assert prune_expired_rate_limits(engine=rate_limit_engine, now=now, batch_size=1) == 1
    with rate_limit_engine.connect() as conn:
        remaining = conn.execute(
            text("SELECT bucket_key FROM auth_rate_limit_buckets")
        ).scalars().all()
    assert remaining == [future_key]


@pytest.mark.parametrize("batch_size", [0, -1, 10001, True, 1.5, "10", None])
def test_cleanup_rejects_invalid_batch_size_before_database_access(rate_limit_engine, batch_size):
    with pytest.raises(ValueError, match="batch_size"):
        prune_expired_rate_limits(engine=rate_limit_engine, batch_size=batch_size)


def test_cleanup_rejects_naive_datetime_before_database_access(rate_limit_engine):
    with pytest.raises(ValueError, match="zona horaria"):
        prune_expired_rate_limits(
            engine=rate_limit_engine,
            now=datetime(2026, 11, 8, 12, 0),
        )
