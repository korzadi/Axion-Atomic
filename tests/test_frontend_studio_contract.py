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
    assert "fetch(API+'/workspace/knowledge/ingest'" in source
    assert "X-CSRF-Token" in source
    assert "project_id:projectId" in source
    assert "El backend valida permisos" in source
    assert "document.querySelector('[data-view=\"chat\"]')" in source


def test_agent_workspace_uses_real_project_scoped_plan_endpoint():
    source = FRONTEND.read_text(encoding="utf-8")
    assert "async function renderAgents()" in source
    assert "if(v==='agents')return renderAgents()" in source
    assert "fetch(API+'/workspace/agent/tasks'" in source
    assert "X-CSRF-Token" in source
    assert "project_id:projectId,goal:text" in source
    assert "Este plan todavía no se ha ejecutado" in source
