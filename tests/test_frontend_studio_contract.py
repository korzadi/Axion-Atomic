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
    assert "Precios y cuotas pendientes de aprobación" in source


def test_optional_newsletter_markup_cannot_abort_landing_reveal():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "var newsletterForm=document.getElementById('nlf');if(newsletterForm)" in source
    assert "document.getElementById('nlf').onsubmit" not in source
    assert "new IntersectionObserver" in source
    assert "document.querySelectorAll('.rv').forEach(function(x){io.observe(x)})" in source


def test_public_indicators_are_loaded_from_backend_not_fake_counters():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "/billing/catalog" in source
    assert "/health/live" in source
    assert 'id="modelCount"' in source
    assert 'id="apiState"' in source
    assert 'id="billingState"' in source
    assert 'data-n="100"' not in source

def test_atomic_code_exposes_only_backend_supported_generation_controls():
    source = FRONTEND.read_text(encoding="utf-8")
    assert 'id="ws-temperature"' in source
    assert 'id="ws-max-tokens"' in source
    for value in ('value="0"', 'value="0.2"', 'value="0.5"', 'value="0.8"', 'value="1.2"'):
        assert value in source
    for value in ('value="1024"', 'value="2048"', 'value="4096"', 'value="8192"'):
        assert value in source


def test_atomic_code_sends_user_selected_generation_settings_to_real_api():
    workspace = (FRONTEND.parent / "workspace.js").read_text(encoding="utf-8")
    assert 'temperature: Number($("ws-temperature").value)' in workspace
    assert 'max_tokens: Number.parseInt($("ws-max-tokens").value, 10)' in workspace
    assert 'temperature: 0.2, max_tokens: 2048' not in workspace
    assert '"/workspace/chat/completions"' in workspace

def test_workspace_sends_stable_idempotency_key_for_metered_chat_retries():
    workspace = (FRONTEND.parent / "workspace.js").read_text(encoding="utf-8")
    assert 'headers: { "Idempotency-Key": pendingIdempotencyKey }' in workspace
    assert "function createIdempotencyKey()" in workspace
    assert "pendingRequestFingerprint !== requestFingerprint" in workspace
    assert "pendingIdempotencyKey = null;" in workspace


def test_chat_discloses_shadow_billing_state_without_claiming_a_charge():
    workspace = (FRONTEND.parent / "workspace.js").read_text(encoding="utf-8")
    assert 'const billing = data.usage_billing;' in workspace
    assert 'billing.mode === "shadow"' in workspace
    assert 'billing.charged === false' in workspace
    assert 'billing.credits_reserved === false' in workspace
    assert "no se cobraron ni reservaron créditos" in workspace
    assert "Estado de facturación no confirmado." in workspace


def test_chat_discloses_measured_ledger_charge_when_billing_is_enabled():
    workspace = (FRONTEND.parent / "workspace.js").read_text(encoding="utf-8")
    assert 'billing.mode === "ledger"' in workspace
    assert 'billing.charged === true' in workspace
    assert 'Number.isSafeInteger(billing.credits_charged)' in workspace
    assert "créditos según el consumo medido de Ollama" in workspace


def test_workspace_locks_project_switching_while_inference_is_running():
    source = (FRONTEND.parent / "workspace.js").read_text(encoding="utf-8")
    assert "function setBusy(value)" in source
    assert "projectSelect.disabled = busy" in source
    assert '$("ws-create-project").disabled = busy' in source
    assert '$("ws-new-project").disabled = busy' in source
    assert 'form.setAttribute("aria-busy", busy ? "true" : "false")' in source
    assert "setBusy(true);" in source
    assert "finally { setBusy(false); }" in source


def test_email_verification_link_uses_registered_api_route():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "api('/auth/verify-email'" in source
    assert "api('/auth/email/verify'" not in source
    assert "api('/auth/password/forgot'" in source
    assert "api('/auth/password/reset'" in source
    assert "api('/auth/resend-verification'" in source
    assert 'id="resend"' in source



def test_chat_retry_preserves_original_payload_after_ambiguous_http_failure():
    workspace = (FRONTEND.parent / "workspace.js").read_text(encoding="utf-8")
    catch_block = workspace.split("} catch (error) {", 1)[1].split("} finally", 1)[0]
    assert "prompt.value = content;" in catch_block
    assert "renderHistory(history);" in catch_block
    assert "await loadHistory()" not in catch_block
    assert "pendingIdempotencyKey" in workspace
    assert "pendingRequestFingerprint" in workspace
