"""Provisioning seguro y explícito de directorios de proyecto.

No crea la raíz configurada ni modifica directorios existentes. Cada proyecto
se crea como hijo directo, con permisos privados y sin seguir symlinks.
"""
import os
import re
import stat
from pathlib import Path

from agent.workspace import PathViolation

_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def provision_project_workspace(root: str | Path, project_id: str) -> Path:
    """Crea <root>/<project_id> de forma exclusiva; devuelve su ruta validada."""
    if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
        raise PathViolation("Identificador de proyecto inválido")
    base = Path(root).resolve(strict=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        root_fd = os.open(base, flags)
    except OSError as exc:
        raise PathViolation("La raíz de workspaces no es un directorio seguro") from exc
    try:
        created = False
        try:
            os.mkdir(project_id, 0o700, dir_fd=root_fd)
            created = True
        except FileExistsError:
            pass
        try:
            child_fd = os.open(project_id, flags, dir_fd=root_fd)
        except OSError as exc:
            raise PathViolation("El workspace existente no es un directorio real") from exc
        try:
            info = os.fstat(child_fd)
            if not stat.S_ISDIR(info.st_mode):
                raise PathViolation("El workspace no es un directorio")
            if created and stat.S_IMODE(info.st_mode) != 0o700:
                os.fchmod(child_fd, 0o700)
        finally:
            os.close(child_fd)
    finally:
        os.close(root_fd)
    return base / project_id
