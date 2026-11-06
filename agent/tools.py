"""Compatibilidad con el starter: delega en agent.workspace (única implementación de seguridad de rutas)."""
from pathlib import Path

from agent.workspace import Workspace, resolve_within
from api.config import settings


def safe_workspace_path(relative_path: str) -> Path:
    return resolve_within(Path(settings.workspace_root), relative_path)


def read_workspace_file(relative_path: str, max_bytes: int = 200000) -> str:
    # Ahora también deniega archivos sensibles/excluidos y redacta secretos (el starter los leía tal cual).
    return Workspace(settings.workspace_root, "default", max_read_bytes=max_bytes).read(relative_path)


def execute_command(*args, **kwargs):
    raise PermissionError("La ejecución de comandos solo estará disponible a través del sandbox (Fase 6).")
