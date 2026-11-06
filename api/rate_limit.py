"""Rate limiting distribuido PostgreSQL con incremento atómico por ventana fija.

El caller debe proporcionar un subject estable y normalizado (por ejemplo IP
normalizada o email casefold); el valor en claro nunca se persiste.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


def _utc(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now debe incluir zona horaria")
    return value.astimezone(timezone.utc)


def rate_limit_key(namespace: str, subject: str) -> str:
    """Deriva clave no reversible práctica; no enviar secretos ni datos sensibles."""
    if not isinstance(namespace, str) or not re.fullmatch(r"[a-z0-9:_-]{1,80}", namespace):
        raise ValueError("namespace no válido")
    if not isinstance(subject, str) or not subject or len(subject) > 512:
        raise ValueError("subject no válido")
    return hashlib.sha256((namespace + ":" + subject).encode("utf-8")).hexdigest()


def consume_rate_limit(
    *, engine: Engine, bucket_key: str, limit: int,
    window: timedelta, now: datetime | None = None,
) -> RateLimitDecision:
    """Consume una solicitud en PostgreSQL; no depende de memoria local."""
    if not isinstance(bucket_key, str) or not _HEX.fullmatch(bucket_key):
        raise ValueError("bucket_key debe ser SHA-256 hexadecimal")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1_000_000:
        raise ValueError("limit no válido")
    if not isinstance(window, timedelta) or window <= timedelta(0) or window > timedelta(days=7):
        raise ValueError("window no válida")
    instant = _utc(now)
    seconds = int(window.total_seconds())
    start = datetime.fromtimestamp((int(instant.timestamp()) // seconds) * seconds, timezone.utc)
    expires = start + window
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO auth_rate_limit_buckets(bucket_key,window_start,hit_count,expires_at)
            VALUES (:key,:start,1,:expires)
            ON CONFLICT(bucket_key,window_start) DO UPDATE
              SET hit_count = auth_rate_limit_buckets.hit_count + 1
              WHERE auth_rate_limit_buckets.hit_count < :limit
            RETURNING hit_count
        """), {"key": bucket_key, "start": start, "expires": expires, "limit": limit}).first()
        if row is not None:
            return RateLimitDecision(True, max(0, limit - row[0]), 0)
        remaining_seconds = max(1, int((expires - instant).total_seconds()))
        return RateLimitDecision(False, 0, remaining_seconds)


def prune_expired_rate_limits(*, engine: Engine, now: datetime | None = None, batch_size: int = 1000) -> int:
    """Limpieza acotada; invocar desde tarea operativa, nunca en cada request."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 10000:
        raise ValueError("batch_size no válido")
    instant = _utc(now)
    with engine.begin() as conn:
        result = conn.execute(text("""
            DELETE FROM auth_rate_limit_buckets
            WHERE (bucket_key,window_start) IN (
                SELECT bucket_key,window_start FROM auth_rate_limit_buckets
                WHERE expires_at <= :now
                ORDER BY expires_at LIMIT :batch
            )
        """), {"now": instant, "batch": batch_size})
        return result.rowcount
