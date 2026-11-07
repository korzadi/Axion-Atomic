"""Lectura privada de métricas de inferencia por usuario y proyecto."""
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from sqlalchemy import text

from api.auth import COOKIE_NAME, authorize_project, current_user
from api.config import settings
from api.database import engine

router = APIRouter(prefix="/workspace", tags=["workspace-usage"])


def _enabled_user(axion_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    """Comprueba el interruptor antes de consultar la base de datos de sesiones."""
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="La autenticación web aún no está habilitada")
    return current_user(axion_session)


@router.get("/usage")
def project_usage(
    project_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(_enabled_user),
):
    """Devuelve solo métricas del usuario autenticado dentro del proyecto autorizado."""
    authorize_project(user["id"], project_id, ("owner", "admin", "editor", "viewer"))
    with engine.connect() as conn:
        totals = conn.execute(text("""
            SELECT COUNT(*) AS requests,
                   COUNT(prompt_tokens) AS measured_prompt_requests,
                   COUNT(output_tokens) AS measured_output_requests,
                   SUM(prompt_tokens) AS prompt_tokens,
                   SUM(output_tokens) AS output_tokens,
                   COUNT(*) FILTER (WHERE usage_source = 'unavailable') AS unavailable_measurements
            FROM inference_usage_events
            WHERE user_id = :user_id AND project_id = :project_id
        """), {"user_id": user["id"], "project_id": project_id}).mappings().one()
        rows = conn.execute(text("""
            SELECT request_id, requested_model, returned_model,
                   prompt_tokens, output_tokens, usage_source, done, observed_at
            FROM inference_usage_events
            WHERE user_id = :user_id AND project_id = :project_id
            ORDER BY observed_at DESC, request_id DESC
            LIMIT :limit
        """), {"user_id": user["id"], "project_id": project_id, "limit": limit}).mappings().all()

    return {
        "project_id": project_id,
        "totals": dict(totals),
        "items": [dict(row) for row in rows],
    }
