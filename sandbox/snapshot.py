"""Copia temporal del proyecto para ejecutar código. Excluye lo sensible/ignorado (el sandbox nunca ve .env ni claves),
omite symlinks, rechaza enlaces duros y limita tamaño. Las aperturas usan descriptores relativos al root y O_NOFOLLOW
para evitar que un symlink concurrente convierta el snapshot en una lectura fuera del proyecto."""
import os
import shutil
import stat
import tempfile
from pathlib import Path

from agent.workspace import Workspace
from core.errors import AxionError


class SnapshotTooLarge(AxionError):
    code = "snapshot_too_large"


class Snapshot:
    def __init__(self, ws: Workspace, max_bytes: int = 200_000_000, max_files: int = 20_000, base_dir: str | None = None):
        self.ws, self.max_bytes, self.max_files, self.base_dir = ws, max_bytes, max_files, base_dir
        self.path: Path | None = None

    @staticmethod
    def _open_regular_file(root_fd: int, rel: str) -> tuple[int, os.stat_result]:
        """Abre rel sin seguir symlinks en ningún componente del path."""
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            raise OSError("El sistema no ofrece O_NOFOLLOW/O_DIRECTORY; snapshot seguro no disponible")
        parts = Path(rel).parts
        if not parts or any(part in ("", ".", "..") for part in parts):
            raise OSError("Ruta inválida en snapshot")
        current_fd = os.dup(root_fd)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                         dir_fd=current_fd)
        finally:
            os.close(current_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise OSError("El snapshot solo admite archivos regulares")
            if info.st_nlink > 1:
                raise OSError("El snapshot rechaza archivos con enlaces duros")
            return fd, info
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix="axion-sbx-", dir=self.base_dir))
        try:
            total = count = 0
            root_fd = os.open(self.ws.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                for rel in self.ws.walk(self.max_files + 1):
                    count += 1
                    if count > self.max_files:
                        raise SnapshotTooLarge("El proyecto contiene demasiados archivos para el sandbox")
                    dst = self.path / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    src_fd, info = self._open_regular_file(root_fd, rel)
                    try:
                        if info.st_size > self.max_bytes - total:
                            raise SnapshotTooLarge("El proyecto es demasiado grande para copiarlo al sandbox")
                        copied = 0
                        src = os.fdopen(src_fd, "rb")
                        src_fd = -1
                        with src:
                            with open(dst, "xb") as target:
                                while True:
                                    chunk = src.read(min(1024 * 1024, self.max_bytes - total - copied + 1))
                                    if not chunk:
                                        break
                                    copied += len(chunk)
                                    if copied > self.max_bytes - total:
                                        raise SnapshotTooLarge("El proyecto es demasiado grande para copiarlo al sandbox")
                                    target.write(chunk)
                        os.chmod(dst, stat.S_IMODE(info.st_mode))
                        total += copied
                    finally:
                        if src_fd >= 0:
                            os.close(src_fd)
            finally:
                os.close(root_fd)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self.path

    def __exit__(self, *exc) -> None:
        if self.path and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
