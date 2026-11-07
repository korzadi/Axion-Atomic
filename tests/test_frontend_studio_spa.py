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
    assert '<style id="axyron-hidden-state-fix">[hidden]{display:none!important}</style>' in html


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
    ):
        assert endpoint in source
    assert "Próxima actualización" in source
    assert "checkout_enabled" in source
    assert "/admin/access/me" not in source
    for section in ("privacidad", "integraciones", "herramientas"):
        assert '"' + section + '"' in source


def test_spa_has_no_fake_admin_or_commercial_mutations():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    assert "/admin/users" not in source
    assert "/billing/checkout" not in source
    assert "payment_intent" not in source
    assert 'const canDecide=["owner","admin"]' in source
    assert "Solo propietario o administrador" in source


def test_admin_portal_is_separate_and_host_routed():
    main = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
    portal = (FRONTEND / "admin.html").read_text(encoding="utf-8")
    admin_js = (FRONTEND / "admin.js").read_text(encoding="utf-8")
    studio = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    assert 'host == "admin.axyronatomic.com"' in main
    assert "ADMIN_PAGE" in main
    assert 'src="/admin.js"' in portal
    assert '/admin/access/me' in admin_js
    assert '["admin"' not in studio


def test_admin_portal_preserves_logout_for_authenticated_non_admin():
    admin_js = (ROOT / "frontend" / "admin.js").read_text(encoding="utf-8")
    admin_html = (ROOT / "frontend" / "admin.html").read_text(encoding="utf-8")
    assert "function showDenied()" in admin_js
    assert "if(!d.administration_enabled){showDenied();return}" in admin_js
    assert 'api("/auth/me").then(()=>loadAccess()).catch(()=>showLogin())' in admin_js
    assert 'id="logout"' in admin_html
    assert 'api("/auth/logout"' in admin_js
