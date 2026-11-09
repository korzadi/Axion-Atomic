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
    # AXYRON Studio ahora es una aplicación independiente; la web principal
    # enlaza por SSO hacia ella, no a una sección escondida.
    assert 'href="/sso-start"' in html
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
        "/workspace/agent/runs/",
        "/workspace/agent/approvals",
        "/workspace/usage",
        "/billing/orders",
        "/billing/credits",
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


def test_model_page_uses_authenticated_live_ollama_availability_not_static_catalog_claims():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    assert '"/workspace/models/availability?project_id="' in source
    assert 'm.available===true' in source
    assert 'Comprobando modelos en Ollama' in source
    assert 'No se pudo verificar Ollama' in source
    assert 'No disponible' in source


def test_billing_view_displays_only_real_credit_balance_and_ledger():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    assert 'api("/billing/credits")' in source
    assert 'credits.totals.available' in source
    assert 'credits.totals.reserved' in source
    assert 'credits.totals.consumed' in source
    assert 'credits.recent_ledger' in source
    assert "Todavía no hay créditos en esta cuenta" in source
    assert "proceden de PostgreSQL" in source


def test_billing_view_uses_real_checkout_contract_when_enabled():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    assert 'api("/billing/checkout/orders",{method:"POST"' in source
    assert '"/verify",{method:"POST"}' in source
    assert 'href="#app/comprar?product_code=' in source
    assert "Crear factura y pagar" in source
    assert "catalog.checkout_enabled===true" in source


def test_studio_dashboard_uses_full_readiness_not_liveness_only():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    assert 'api("/health")' in source
    assert 'readiness.status==="ok"?"Servicios operativos":"Servicios degradados"' in source
    assert 'api("/health/live")' not in source
    assert "healthClass" in source


def test_integrations_and_extensions_are_explicitly_future_features():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for label in (
        "AXYRON CONNECT",
        "Aplicaciones y conectores",
        "Plugins, Skills y Tools",
        "Plugin Hub",
        "Skill Library",
        "Tool Registry",
        "MCP / APIs",
        "Próxima actualización",
        "permisos",
        "revocación",
    ):
        assert label in source
    for label in (
        "Ecosistema extensible",
        "AXYRON CONNECT",
        "App Connectors",
        "Plugin Hub",
        "Skill Library",
        "Tool Registry",
        "Automation Hub",
        "Security Center",
        "MCP",
        "No existe todavía un catálogo operativo",
    ):
        assert label in readme


def test_spa_has_no_fake_admin_or_unregistered_commercial_mutations():
    source = (FRONTEND / "studio.js").read_text(encoding="utf-8")
    assert "/admin/users" not in source
    # El checkout real (aprobado por el propietario el 2026-11-08) solo usa las rutas
    # registradas en el backend; nada de payment_intent ni mutaciones inventadas.
    assert "payment_intent" not in source
    assert '"/billing/subscriptions"' not in source
    assert '"/billing/checkout/orders"' in source
    assert 'canDecide=["owner","admin"].includes(role)' in source
    assert 'canEdit=["owner","admin","editor"].includes(role)' in source
    assert 'x.status==="awaiting_approval"&&canEdit' in source
    assert "Solo propietario o administrador" in source
    assert "data-resume-run" in source
    assert "/resume?project_id=" in source
    assert "Continuar ejecución" in source
    assert "acciones que ya hayan sido aprobadas" in source
    assert "data-reconcile-run" in source
    assert "/reconcile?project_id=" in source
    assert "Marcar aplicada" in source
    assert "Marcar no aplicada" in source
    assert "sin ejecutarla" in source
    assert "data-cancel-run" in source
    assert "/cancel?project_id=" in source
    assert "Cancelar ejecución" in source
    assert "invalidar" in source


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
    assert "billing.manage" in admin_js
    assert '/admin/billing/executions/recover?limit=25&reason=' in admin_js
    assert '/admin/billing/reservations/reconcile-no-execution' in admin_js
    assert "users.manage" in admin_js
    assert 'renderUserManagement()' in admin_js
    assert '/roles' in admin_js
    assert '/status' in admin_js
    assert "de solo lectura" not in admin_js


def test_admin_portal_preserves_logout_for_authenticated_non_admin():
    admin_js = (ROOT / "frontend" / "admin.js").read_text(encoding="utf-8")
    admin_html = (ROOT / "frontend" / "admin.html").read_text(encoding="utf-8")
    assert "function showDenied()" in admin_js
    assert "if(!d.administration_enabled){showDenied();return}" in admin_js
    assert 'api("/auth/me").then(()=>loadAccess()).catch(()=>showLogin())' in admin_js
    assert 'id="logout"' in admin_html
    assert 'api("/auth/logout"' in admin_js
    assert '$("login-form").classList.add("hidden")' in admin_js
    assert '$("password").value=""' in admin_js
    assert '$("mfa-code").focus()' in admin_js
