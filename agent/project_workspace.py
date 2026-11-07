"""Resolución segura y composición de herramientas por proyecto.

El identificador procede de la capa de autorización, nunca de una ruta enviada
por el cliente. Esta fábrica no crea directorios ni concede autorización.
"""
import os
import re
import stat
from pathlib import Path
from typing import Callable

from agent.git import GitManager
from agent.toolset import build_tools
from agent.workspace import PathViolation, Workspace
from sandbox.backends import DockerBackend


_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def project_workspace(root: str | Path, project_id: str) -> Workspace:
    """Resuelve un workspace real, hijo directo y con permisos estrictamente privados.

    El llamador debe autenticar al usuario y verificar su membresía antes de
    invocar esta función. No cambia permisos de directorios existentes: si el
    workspace permite acceso a grupo/otros, falla de forma cerrada.
    """
    if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
        raise PathViolation("Identificador de proyecto inválido")

    base = Path(root).resolve(strict=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        root_fd = os.open(base, flags)
    except OSError as exc:
        raise PathViolation("La raíz de workspaces no es un directorio seguro") from exc
    try:
        try:
            child_fd = os.open(project_id, flags, dir_fd=root_fd)
        except FileNotFoundError:
            raise PathViolation("El workspace del proyecto no existe") from None
        except OSError as exc:
            raise PathViolation("El workspace debe ser un directorio real, no un symlink") from exc
        try:
            info = os.fstat(child_fd)
            if not stat.S_ISDIR(info.st_mode):
                raise PathViolation("El workspace debe ser un directorio")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise PathViolation("El workspace debe tener permisos privados (700 o más restrictivos)")
        finally:
            os.close(child_fd)
    finally:
        os.close(root_fd)

    resolved = (base / project_id).resolve(strict=True)
    if resolved.parent != base:
        raise PathViolation("El workspace sale de la raíz autorizada")
    return Workspace(resolved, project_id)


def build_project_toolset(
    root: str | Path,
    project_id: str,
    *,
    backend=None,
    limits=None,
    audit: Callable[[dict], None] | None = None,
    snapshot_dir: str | None = None,
):
    """Compone herramientas ligadas a un único workspace de proyecto.

    Si se solicita ejecución, solo acepta un backend que declare aislamiento
    de contenedor. La autorización HTTP debe realizarse antes de esta llamada.
    """
    workspace = project_workspace(root, project_id)
    git = GitManager(workspace)
    sandbox = None
    if backend is not None:
        if not isinstance(backend, DockerBackend):
            raise PathViolation("El runtime de proyecto exige un backend sandbox aislado por contenedor")
        from sandbox.executor import SandboxExecutor
        sandbox = SandboxExecutor(
            backend=backend,
            ws=workspace,
            limits=limits,
            audit=audit,
            snapshot_dir=snapshot_dir,
        )
    application_root = Path(__file__).resolve().parent.parent
    return workspace, build_tools(
        workspace, git, sandbox=sandbox, skill_roots=(application_root,)
    )
