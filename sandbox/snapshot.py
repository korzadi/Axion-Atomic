"""Copia temporal del proyecto para ejecutar código. Excluye lo sensible/ignorado (el sandbox nunca ve .env ni claves),
omite symlinks y limita tamaño. Los cambios hechos dentro NO vuelven al proyecto original."""
import os
import shutil
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

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix="axion-sbx-", dir=self.base_dir))
        try:
            total = count = 0
            for rel in self.ws.walk(self.max_files + 1):
                src = self.ws.root / rel
                count += 1
                total += src.stat().st_size
                if count > self.max_files or total > self.max_bytes:
                    raise SnapshotTooLarge("El proyecto es demasiado grande para copiarlo al sandbox")
                dst = self.path / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                shutil.copymode(src, dst)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self.path

    def __exit__(self, *exc) -> None:
        if self.path and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
