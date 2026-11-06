"""Creación coordinada de proyecto, membresía y workspace.

El directorio se crea exclusivamente (no se reutilizan rutas preexistentes).
Ante fallos SQL se elimina solo si continúa vacío. No se borran datos ajenos.
"""
import os
import secrets
import stat
from pathlib import Path

from sqlalchemy import text

from api.config import settings
from api.database import engine


def _create_workspace_exclusive(root: str | Path, project_id: str) -> Path:
    base = Path(root).resolve(strict=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    root_fd = os.open(base, flags)
    try:
        os.mkdir(project_id, 0o700, dir_fd=root_fd)
        try:
            child_fd = os.open(project_id, flags, dir_fd=root_fd)
        except OSError:
            os.rmdir(project_id, dir_fd=root_fd)
            raise
        try:
            if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                raise NotADirectoryError("workspace is not a directory")
            os.fchmod(child_fd, 0o700)
        finally:
            os.close(child_fd)
    finally:
        os.close(root_fd)
    return base / project_id


def _remove_empty_workspace(root: str | Path, project_id: str) -> None:
    """Retira solo un hijo directo vacío; nunca sigue symlinks."""
    base = Path(root).resolve(strict=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    root_fd = os.open(base, flags)
    try:
        try:
            os.rmdir(project_id, dir_fd=root_fd)
        except OSError:
            # Si contiene datos, desapareció o cambió de tipo, se conserva.
            return
    finally:
        os.close(root_fd)


def create_owned_project_with_workspace(user_id: str, name: str) -> dict:
    """Crea proyecto, membresía owner y workspace; compensa fallos de commit."""
    clean_name = name.strip() if isinstance(name, str) else ""
    if not user_id or len(clean_name) < 2 or len(clean_name) > 120:
        raise ValueError("Datos del proyecto no válidos")

    project_id = secrets.token_urlsafe(24)
    membership_id = secrets.token_urlsafe(24)
    root = settings.workspace_root
    workspace_created = False

    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
                {"id": project_id, "name": clean_name},
            )
            conn.execute(
                text(
                    "INSERT INTO project_memberships "
                    "(id, project_id, user_id, role, created_by) "
                    "VALUES (:id, :project_id, :user_id, 'owner', :created_by)"
                ),
                {
                    "id": membership_id,
                    "project_id": project_id,
                    "user_id": user_id,
                    "created_by": user_id,
                },
            )
            _create_workspace_exclusive(root, project_id)
            workspace_created = True
    except Exception:
        if workspace_created:
            _remove_empty_workspace(root, project_id)
        raise

    return {"id": project_id, "name": clean_name, "role": "owner"}
