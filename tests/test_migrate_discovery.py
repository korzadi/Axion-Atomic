import pytest
from api import migrate

def test_discover_orders_and_validates(tmp_path):
    (tmp_path / "002_b.sql").write_text("SELECT 1;")
    (tmp_path / "001_a.sql").write_text("SELECT 1;")
    assert [v for v, _ in migrate.discover(tmp_path)] == ["001", "002"]

def test_bad_name_rejected(tmp_path):
    (tmp_path / "bad.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError):
        migrate.discover(tmp_path)

def test_duplicate_versions_rejected(tmp_path):
    (tmp_path / "001_a.sql").write_text("x")
    (tmp_path / "001_b.sql").write_text("x")
    with pytest.raises(ValueError):
        migrate.discover(tmp_path)

def test_checksum_changes(tmp_path):
    p = tmp_path / "001_a.sql"; p.write_text("a"); c1 = migrate.checksum(p)
    p.write_text("b"); assert migrate.checksum(p) != c1
