"""Contratos estáticos de la SPA autenticada Axyron Studio."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_spa_assets_are_linked_from_the_selected_landing_page():
    html = (FRONTEND / "Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html").read_text(encoding="utf-8")
    assert 'id="studio-shell"' in html
    assert 'id="studio-nav"' in html
    assert 'href="/studio.css"' in html
    assert 'src="/studio.js"' in html
    assert 'href="#app/inicio"' in html


def test_spa_uses_only_existing_backend_routes_for_available_modules():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    for endpoint in (
        "/auth/me",
        "/auth/projects",
        "/billing/catalog",
        "/workspace/knowledge/sources",
        "/workspace/knowledge/upload",
        "/workspace/knowledge/ingest",
        "/workspace/agent/runs",
        "/workspace/agent/approvals",
        "/workspace/usage",
        "/billing/orders",
        "/auth/mfa/status",
        "/auth/mfa/enroll",
        "/auth/mfa/confirm",
        "/admin/access/me",
    ):
        assert endpoint in source
    assert "Próxima actualización" in source
    assert "checkout_enabled" in source
    assert "Mutaciones deshabilitadas" in source
    for section in ("privacidad", "integraciones", "herramientas"):
        assert '"' + section + '"' in source


def test_spa_has_no_fake_admin_or_commercial_mutations():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    assert "/admin/users" not in source
    assert "/billing/checkout" not in source
    assert "payment_intent" not in source
