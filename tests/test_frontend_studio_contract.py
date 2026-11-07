"""Contratos estáticos para la landing pública de Axyron Atomic."""
from pathlib import Path

FRONTEND = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html"
)


def test_landing_uses_real_authentication_and_public_api_endpoints():
    source = FRONTEND.read_text(encoding="utf-8")
    for endpoint in (
        "/auth/register",
        "/auth/login",
        "/auth/me",
        "/auth/logout",
        "/auth/password/forgot",
        "/auth/mfa/challenge/verify",
        "/billing/catalog",
        "/health/live",
    ):
        assert endpoint in source
    assert "terms_accepted:true" in source
    assert "X-CSRF-Token" in source


def test_landing_does_not_create_fake_browser_sessions():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "axyron-user" not in source
    assert "TODO: conectar con tu API de autenticación real" not in source
    assert "localStorage.setItem('axyron-user'" not in source


def test_unreleased_models_and_commercial_features_are_roadmap_items():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "Atomic Video" in source and "Próxima actualización" in source
    assert "Atomic Vision" in source
    assert "Atomic Reasoning" in source
    assert "Checkout deshabilitado" in source
    assert "precios y cuotas pendientes de aprobación" in source


def test_public_indicators_are_loaded_from_backend_not_fake_counters():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "/billing/catalog" in source
    assert "/health/live" in source
    assert 'id="modelCount"' in source
    assert 'id="apiState"' in source
    assert 'id="billingState"' in source
    assert 'data-n="100"' not in source
