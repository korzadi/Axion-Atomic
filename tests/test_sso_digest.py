"""El hash del SSO no debe fallar con entradas no ASCII."""
import hashlib

from api.sso_routes import _digest


def test_digest_accepts_non_ascii_without_raising():
    value = "ñandú-状態-🔐"
    assert _digest(value) == hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_digest_is_stable_and_distinct():
    assert _digest("estado") == _digest("estado")
    assert _digest("estado") != _digest("estado ")
