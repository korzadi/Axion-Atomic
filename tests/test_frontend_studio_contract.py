"""Contratos estáticos mínimos para los flujos visibles de AXION STUDIO.

Estas pruebas verifican cableado de frontend, no sustituyen pruebas de navegador
ni pruebas de integración HTTP contra una instancia desplegada.
"""
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


def test_authenticated_home_uses_real_account_and_catalog_endpoints():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "async function renderHome(user={})" in source
    assert "fetch(API+'/auth/projects'" in source
    assert "fetch(API+'/billing/catalog'" in source
    assert "await renderHome(d.user||user||{})" in source
    assert "data-home-view=\"projects\"" in source
    assert "data-home-view=\"chat\"" in source
    assert "data-home-view=\"models\"" in source


def test_home_dashboard_does_not_claim_runtime_or_billing_availability():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "no es una prueba de runtime" in source
    assert "checkout_enabled" in source
    assert "El panel no muestra saldos ni disponibilidad de inferencia" in source


def test_home_navigation_routes_to_existing_workspace_views():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "if(v==='home')return renderHome()" in source
    assert "if(v==='projects')return renderProjects()" in source
    assert "if(v==='chat')return renderChat()" in source
    assert "if(v==='models')return renderModels()" in source


def test_knowledge_workspace_uses_authenticated_project_scoped_ingestion():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "async function renderKnowledge()" in source
    assert "workspace/knowledge/ingest" in source
    assert "X-CSRF-Token" in source
    assert "project_id:projectId" in source
    assert "canEdit()" in source
    assert "data-view=" in source


def test_knowledge_workspace_lists_reindexes_and_deletes_project_sources():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "workspace/knowledge/sources?" in source
    assert "method:'PUT'" in source
    assert "method:'DELETE'" in source
    assert "¿Eliminar todos los fragmentos" in source
    assert "Reindexar con el editor" in source
    assert "legacy" in source

def test_agent_workspace_uses_persistent_project_scoped_runtime():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "async function renderAgents()" in source
    assert "if(v==='agents')return renderAgents()" in source
    assert "fetch(API+'/workspace/agent/runs'" in source
    assert "X-CSRF-Token" in source
    assert "project_id:projectId,goal:text" in source
    assert "Runtime ejecutado y snapshot guardado" in source


def test_agent_workspace_starts_persistent_runtime_and_supports_resume():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "fetch(API+'/workspace/agent/runs'" in source
    assert "X-CSRF-Token" in source
    assert "Reanudar ejecución" in source
    assert "/resume?project_id=" in source
    assert "Las modificaciones no se aplican hasta que un propietario o administrador las apruebe" in source


def test_chat_workspace_restores_private_history_before_enabling_send():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "workspace/chat/history?project_id=" in source
    assert "historyReady=false" in source
    assert "if(request!==historyRequest||select.value!==projectId)return" in source
    assert "send.disabled=!select.value||!historyReady||chatInFlight" in source
    assert "historyReady=false;notice.textContent=error.message" in source


def test_chat_workspace_saves_successful_turn_and_restores_failed_turn():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "workspace/chat/completions" in source
    assert "messages=[...next,{role:'assistant',content:answer}]" in source
    assert "messages=previous;draw();input.value=value" in source
    assert "Respuesta recibida y guardada en el historial del proyecto." in source


def test_chat_workspace_sends_csrf_and_does_not_send_while_history_is_unavailable():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "'X-CSRF-Token':decodeURIComponent(cookie('axion_csrf'))" in source
    assert "if(!value||!projectId||!historyReady||chatInFlight||send.disabled)return" in source
    assert "select.addEventListener('change',()=>loadHistory(select.value))" in source

def test_unreleased_modules_are_marked_for_next_update_and_code_uses_real_chat():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "if(v==='chat'||v==='code')return renderChat()" in source
    assert "renderComingSoon('ATOMIC VIDEO'" in source
    assert source.count("Próxima actualización") >= 3
    assert "billing/catalog" in source
