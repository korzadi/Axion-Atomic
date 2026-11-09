"""Contratos de la aplicación independiente AXYRON STUDIO.

Protegen que las vistas usen rutas reales del backend, que el agente no tenga
enlaces ficticios y que el SSO no exponga el código de un solo uso en la query.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "studio"
APP = (STUDIO / "app.js").read_text(encoding="utf-8")
INDEX = (STUDIO / "index.html").read_text(encoding="utf-8")
SSO = (ROOT / "api" / "sso_routes.py").read_text(encoding="utf-8")


def test_studio_is_a_separate_document_with_own_assets():
    assert 'href="/studio.css"' in INDEX
    assert 'src="/app.js"' in INDEX
    assert 'id="st-outlet"' in INDEX
    assert 'meta name="landing-origin"' in INDEX
    assert 'href="/sso-start"' not in INDEX


def test_studio_has_real_routes_for_every_sidebar_section():
    for route in (
        "dashboard", "projects", "code", "knowledge", "agent", "models",
        "usage", "billing", "buy", "account", "security", "privacy",
        "integrations", "tools",
    ):
        assert f"{route}: render" in APP
        assert f'data-page="{route}"' in INDEX


def test_agent_view_has_no_fake_links_and_uses_real_contracts():
    assert 'href="#approve"' not in APP
    for endpoint in (
        "/workspace/agent/runs",
        "/workspace/agent/runs/",
        "/workspace/agent/approvals/",
        "/workspace/agent/plan-approvals/",
        "/resume?project_id=",
        "/cancel?project_id=",
        "/reconcile?project_id=",
    ):
        assert endpoint in APP
    assert "Ver detalle" in APP
    assert "Aprobar" in APP and "Rechazar" in APP
    assert "La aprobación no ejecuta por sí sola la acción." in APP
    assert '["owner", "admin"].includes(currentRole())' in APP
    assert '["owner", "admin", "editor"].includes(currentRole())' in APP


def test_agent_run_detail_renders_persisted_snapshot():
    assert "detail.messages" in APP
    assert "detail.pending_actions" in APP
    assert "action_hash" in APP
    assert "needs_reconciliation" in APP
    assert "awaiting_approval" in APP


def test_chat_sends_full_history_with_idempotency_per_payload():
    assert 'model: "atomic-code"' in APP
    assert 'messages: history.concat([{ role: "user", content }])' in APP
    assert '"Idempotency-Key": pendingKey' in APP
    assert "if (!pendingKey || pendingFingerprint !== fingerprint)" in APP
    # La huella de idempotencia ignora stream para que un reintento SSE/JSON
    # no se trate como payload distinto; el cuerpo se envía como JSON.
    assert 'JSON.stringify({ ...payload, stream: false })' in APP
    assert 'body: JSON.stringify(payload)' in APP
    assert "await loadHistory()" in APP
    # Streaming SSE real con fallback/parseo de eventos.
    assert 'stream: true' in APP
    assert 'text/event-stream' in APP
    assert 'event === "done"' in APP


def test_models_view_requires_live_runtime_confirmation():
    assert 'api("/billing/catalog")' in APP
    assert "/workspace/models/availability?project_id=" in APP
    # El catálogo no basta para declarar disponibilidad.
    assert "available === true" in APP
    assert "Disponible ahora" in APP
    assert "El catálogo lo publica, pero el runtime no lo confirmó" in APP
    assert "Atomic Reasoning" in APP and "Atomic Vision" in APP and "Atomic Video" in APP
    assert "Próxima actualización" in APP


def test_projects_can_be_created_selected_and_opened_without_fake_delete():
    assert 'api("/auth/projects"' in APP
    assert "data-select-project" in APP
    assert "data-open-project" in APP
    assert "no expone un endpoint de borrado" in APP
    assert "data-delete-project" not in APP


def test_sso_callback_uses_fragment_and_strips_it_before_exchange():
    assert 'window.location.hash.replace(/^#/, "")' in APP
    assert 'history.replaceState({}, "", "/sso/callback")' in APP
    assert 'api("/auth/sso/exchange"' in APP
    assert "localStorage" not in APP


def test_sso_backend_does_not_put_code_in_query_string():
    assert '/sso/callback#code=' in SSO
    assert '/sso/callback?code=' not in SSO
    assert 'encode("ascii")' not in SSO
    assert 'Cache-Control"] = "no-store"' in SSO


def test_security_view_does_not_claim_unverified_sandbox():
    assert "AGT-04 verificado" not in APP
    assert "fail-closed" in APP
    assert "validación E2E sigue pendiente" in APP
    assert "La ejecución real ocurre solo" not in APP


def test_privacy_copy_does_not_overclaim_encryption_or_deletion():
    assert "historial de chat se guarda cifrado en reposo" not in APP
    assert "no cifrado a nivel de aplicación" in APP
    assert "No hay autoservicio de borrado de proyectos" in APP
    assert 'api("/auth/account/export")' in APP
    assert 'api("/auth/account/deletion-request"' in APP
    assert "eliminación efectiva la revisa y ejecuta el operador" in APP
    assert "no se borra automáticamente" in APP


def test_password_change_is_wired_to_real_backend():
    assert 'api("/auth/password/change"' in APP
    assert "current_password" in APP
    assert "new_password" in APP
    assert "La nueva contraseña y su confirmación no coinciden." in APP
    assert "cambio de contraseña con sesión activa no tiene endpoint" not in APP


def test_logout_scope_is_documented_as_host_only():
    assert "no cierra la web principal ni otras sesiones de tu cuenta" in APP
    assert "no implementa cierre de sesión global" in APP
