from pathlib import Path

import pytest

from api.migrate import checksum, discover


def _write(directory: Path, filename: str, sql: str = "SELECT 1;") -> Path:
    path = directory / filename
    path.write_text(sql, encoding="utf-8")
    return path


def test_discover_orders_versions_numerically(tmp_path):
    _write(tmp_path, "999_legacy.sql")
    _write(tmp_path, "1000_next.sql")
    _write(tmp_path, "010_current.sql")

    discovered = discover(tmp_path)

    assert [version for version, _ in discovered] == ["010", "999", "1000"]


def test_discover_rejects_duplicate_numeric_versions_with_different_padding(tmp_path):
    _write(tmp_path, "001_initial.sql")
    _write(tmp_path, "0001_duplicate.sql")

    with pytest.raises(ValueError, match="duplicadas"):
        discover(tmp_path)


def test_discover_rejects_invalid_migration_filename(tmp_path):
    _write(tmp_path, "not-a-migration.sql")

    with pytest.raises(ValueError, match="Nombre de migración inválido"):
        discover(tmp_path)


def test_checksum_changes_when_migration_content_changes(tmp_path):
    migration = _write(tmp_path, "001_initial.sql", "SELECT 1;")
    initial = checksum(migration)

    migration.write_text("SELECT 2;", encoding="utf-8")

    assert checksum(migration) != initial
