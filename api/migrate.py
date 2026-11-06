"""Migrador SQL versionado. Aplica migrations/NNN_*.sql en orden, una sola vez cada una.

- Tabla schema_migrations (version, checksum, applied_at).
- Lock consultivo de PostgreSQL: dos instancias no migran a la vez.
- Cada migración se ejecuta en su propia transacción.
- Si un archivo ya aplicado cambió (checksum distinto) se aborta: nunca se reescribe historia.
- Nunca borra ni reinicializa datos.
"""
import hashlib
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from api.config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
NAME_RE = re.compile(r"^(\d{3,})_[a-z0-9_]+\.sql$")
LOCK_ID = 7_340_001


def discover(directory: Path = MIGRATIONS_DIR) -> list[tuple[str, Path]]:
    items = []
    for p in sorted(directory.glob("*.sql")):
        m = NAME_RE.match(p.name)
        if not m:
            raise ValueError(f"Nombre de migración inválido: {p.name}")
        items.append((m.group(1), p))
    versions = [v for v, _ in items]
    if len(versions) != len(set(versions)):
        raise ValueError("Versiones de migración duplicadas")
    return items


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(database_url: str | None = None, directory: Path = MIGRATIONS_DIR) -> list[str]:
    engine = create_engine(database_url or settings.database_url, future=True)
    applied_now: list[str] = []
    with engine.connect() as lock_conn:
        lock_conn.execute(text("SELECT pg_advisory_lock(:i)"), {"i": LOCK_ID})
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "version TEXT PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, "
                    "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"))
            with engine.connect() as conn:
                done = {r[0]: r[1] for r in conn.execute(text("SELECT version, checksum FROM schema_migrations"))}
            for version, path in discover(directory):
                digest = checksum(path)
                if version in done:
                    if done[version] != digest:
                        raise RuntimeError(f"La migración {path.name} ya aplicada fue modificada")
                    continue
                with engine.begin() as conn:
                    conn.exec_driver_sql(path.read_text(encoding="utf-8"))
                    conn.execute(text("INSERT INTO schema_migrations(version,name,checksum) VALUES (:v,:n,:c)"),
                                 {"v": version, "n": path.name, "c": digest})
                applied_now.append(path.name)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:i)"), {"i": LOCK_ID})
    return applied_now


if __name__ == "__main__":
    try:
        done = run()
    except Exception as exc:  # noqa: BLE001
        print(f"MIGRATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    print("Aplicadas:", ", ".join(done) if done else "ninguna (al día)")
