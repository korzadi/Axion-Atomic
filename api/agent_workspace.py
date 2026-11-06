"""Frontera de autorización para componer herramientas de un agente.

Este módulo no expone endpoints ni inicia ejecuciones. La identidad debe venir
de current_user; la membresía se comprueba antes de resolver el filesystem.
"""
from pathlib import Path

from api.auth import authorize_project
from api.config import settings
from agent.project_workspace import build_project_toolset


def build_authorized_project_toolset(
    user: dict,
    project_id: str,
    *,
    backend=None,
    limits=None,
    audit=None,
    snapshot_dir: str | None = None,
    workspace_root: str | Path | None = None,
):
    """Autoriza al usuario y compone herramientas limitadas al proyecto.

    Solo owner/admin/editor pueden preparar herramientas de agente. Esta
    función no crea el directorio, no inicia el agente y no evita las
    aprobaciones por acción.
    """
    user_id = user.get("id") if isinstance(user, dict) else None
    if not user_id:
        raise ValueError("Se requiere una identidad autenticada")
    authorize_project(user_id, project_id, ("owner", "admin", "editor"))
    return build_project_toolset(
        workspace_root or settings.workspace_root,
        project_id,
        backend=backend,
        limits=limits,
        audit=audit,
        snapshot_dir=snapshot_dir,
    )
