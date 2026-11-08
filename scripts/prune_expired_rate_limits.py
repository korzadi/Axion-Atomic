"""Limpieza manual y acotada de buckets expirados del rate limiter.

Por defecto solo informa cuántos registros han expirado. Para borrar un único
lote limitado se requiere --apply explícito.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import text

from api.database import engine
from api.rate_limit import prune_expired_rate_limits

MAX_BATCH_SIZE = 10_000
DEFAULT_BATCH_SIZE = 1_000


def _validate_batch_size(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_BATCH_SIZE:
        raise ValueError(f"batch-size debe estar entre 1 y {MAX_BATCH_SIZE}")
    return value


def run_cleanup(*, target_engine, apply: bool = False, batch_size: int = DEFAULT_BATCH_SIZE,
                now: datetime | None = None) -> dict[str, int | str]:
    """Cuenta sin mutar por defecto; --apply elimina como máximo un lote."""
    size = _validate_batch_size(batch_size)
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now debe incluir zona horaria")
    instant = instant.astimezone(timezone.utc)

    if not apply:
        with target_engine.connect() as conn:
            count = conn.execute(text("""
                SELECT COUNT(*) FROM auth_rate_limit_buckets
                WHERE expires_at <= :now
            """), {"now": instant}).scalar_one()
        return {"mode": "dry-run", "expired": int(count), "deleted": 0}

    deleted = prune_expired_rate_limits(
        engine=target_engine, now=instant, batch_size=size,
    )
    return {"mode": "apply", "expired": deleted, "deleted": deleted}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cuenta buckets expirados; elimina un lote solo con --apply."
    )
    parser.add_argument("--apply", action="store_true",
                        help="elimina explícitamente un único lote")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"máximo por ejecución (1-{MAX_BATCH_SIZE}; default {DEFAULT_BATCH_SIZE})")
    args = parser.parse_args(argv)

    try:
        result = run_cleanup(
            target_engine=engine, apply=args.apply, batch_size=args.batch_size,
        )
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))

    print(
        f"rate-limit cleanup: mode={result['mode']} "
        f"expired={result['expired']} deleted={result['deleted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
