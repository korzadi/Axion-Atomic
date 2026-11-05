"""File Manager: acceso confinado a un directorio de proyecto. Lectura libre (con redacción de secretos),
escritura solo mediante propuestas que requieren una aprobación ligada al hash exacto del cambio."""
import difflib
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from agent.approval_gate import ActionProposal, ApprovedAction
from agent.ignore import IgnoreRules
from agent.secrets import find_secrets, is_sensitive_path, redact
from core.errors import AxionError

MAX_WRITE_BYTES = 1_000_000


class PathViolation(AxionError, ValueError):
    code = "path_violation"


class AccessDenied(AxionError):
    code = "access_denied"


class ConflictError(AxionError):
    code = "conflict"


def resolve_within(root: Path, rel: str) -> Path:
    """Resuelve rel dentro de root (sigue symlinks) o lanza PathViolation. No exige que exista."""
    if "\0" in rel:
        raise PathViolation("Ruta inválida")
    if rel.startswith(("/", "\\")) or (len(rel) > 1 and rel[1] == ":"):
        raise PathViolation("Se requieren rutas relativas al proyecto")
    base = Path(root).resolve()
    target = (base / rel).resolve()
    if target != base and base not in target.parents:
        raise PathViolation("La ruta sale del proyecto")
    return target


@dataclass(frozen=True)
class ProposedChange:
    kind: str                    # write | create | delete
    rel: str
    before_sha: str | None
    new_content: str | None
    diff: str
    proposal: ActionProposal


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Workspace:
    def __init__(self, root: str | Path, project_id: str, max_read_bytes: int = 200_000):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise PathViolation("El directorio del proyecto no existe")
        self.project_id, self.max_read_bytes = project_id, max_read_bytes
        self.ignore = IgnoreRules.for_root(self.root)

    # ---------- utilidades
    def resolve(self, rel: str) -> Path:
        return resolve_within(self.root, rel)

    def relpath(self, p: Path) -> str:
        # sin resolver el último componente: un symlink se identifica por su nombre, no por su destino
        return Path(os.path.abspath(p)).relative_to(self.root).as_posix()

    def _check_readable(self, rel: str) -> Path:
        path = self.resolve(rel)
        r = self.relpath(path) if path != self.root else "."
        if r != "." and (is_sensitive_path(r) or self.ignore.is_ignored(r, path.is_dir())):
            raise AccessDenied(f"Acceso denegado (archivo sensible o excluido): {r}")
        return path

    # ---------- lectura
    def read(self, rel: str, start_line: int | None = None, end_line: int | None = None) -> str:
        path = self._check_readable(rel)
        if not path.is_file():
            raise FileNotFoundError(rel)
        if path.stat().st_size > self.max_read_bytes and start_line is None:
            raise AccessDenied(f"Archivo mayor que {self.max_read_bytes} bytes: usa start_line/end_line")
        raw = path.read_bytes()
        if b"\0" in raw[:8192]:
            raise AccessDenied("Archivo binario")
        text = raw.decode("utf-8", errors="replace")
        if start_line is not None:
            lines = text.splitlines()
            lo = max(start_line, 1) - 1
            hi = min(end_line or lo + 200, lo + 400)
            text = "\n".join(f"{i + 1}: {l}" for i, l in enumerate(lines[lo:hi], lo))
        return redact(text)

    def list_dir(self, rel: str = ".") -> list[dict]:
        path = self._check_readable(rel)
        if not path.is_dir():
            raise NotADirectoryError(rel)
        out = []
        for child in sorted(path.iterdir()):
            r = self.relpath(child)
            if child.is_symlink() or is_sensitive_path(r) or self.ignore.is_ignored(r, child.is_dir()):
                continue
            out.append({"name": child.name, "type": "dir" if child.is_dir() else "file",
                        "size": child.stat().st_size if child.is_file() else None})
        return out

    def walk(self, max_files: int = 5000) -> Iterator[str]:
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            d = Path(dirpath)
            dirnames[:] = sorted(n for n in dirnames
                                 if not (d / n).is_symlink()
                                 and not self.ignore.is_ignored(self.relpath(d / n), True)
                                 and not is_sensitive_path(self.relpath(d / n) + "/x"))
            for n in sorted(filenames):
                p = d / n
                r = self.relpath(p)
                if p.is_symlink() or is_sensitive_path(r) or self.ignore.is_ignored(r, False):
                    continue
                yield r
                count += 1
                if count >= max_files:
                    return

    def search(self, query: str, glob: str | None = None, max_results: int = 50, case_sensitive: bool = False) -> list[dict]:
        if not query:
            raise ValueError("Consulta vacía")
        needle = query if case_sensitive else query.lower()
        out = []
        for r in self.walk():
            if glob and not Path(r).match(glob):
                continue
            p = self.root / r
            if p.stat().st_size > self.max_read_bytes:
                continue
            raw = p.read_bytes()
            if b"\0" in raw[:8192]:
                continue
            for no, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
                if needle in (line if case_sensitive else line.lower()):
                    out.append({"path": r, "line": no, "text": redact(line.strip())[:200]})
                    if len(out) >= max_results:
                        return out
        return out

    # ---------- propuestas de escritura (no modifican nada)
    def _writable(self, rel: str) -> Path:
        path = self.resolve(rel)
        r = self.relpath(path)
        if is_sensitive_path(r) or r == ".git" or r.startswith(".git/"):
            raise AccessDenied(f"Escritura denegada: {r}")
        return path

    def _make(self, kind: str, rel: str, before: bytes | None, new: str | None, why: str) -> ProposedChange:
        old_text = before.decode("utf-8", "replace") if before is not None else ""
        diff = "".join(difflib.unified_diff(old_text.splitlines(True), (new or "").splitlines(True),
                                            f"a/{rel}", f"b/{rel}"))
        risks = []
        if new and find_secrets(new):
            risks.append("El nuevo contenido parece incluir secretos/credenciales")
        if kind == "delete":
            risks.append("Eliminación de archivo: recuperable solo mediante control de versiones")
        before_sha = _sha(before) if before is not None else None
        fp = _sha(f"{kind}|{before_sha}|{new}".encode())
        prop = ActionProposal(self.project_id, f"fs.{kind}", f"{kind} {rel}", why, (rel,), diff[:20000] or "(sin cambios)",
                              tuple(risks), "El archivo queda con el contenido mostrado" if kind != "delete" else "El archivo desaparece",
                              fp)
        return ProposedChange(kind, rel, before_sha, new, diff, prop)

    def propose_write(self, rel: str, content: str, why: str) -> ProposedChange:
        path = self._writable(rel)
        if len(content.encode()) > MAX_WRITE_BYTES:
            raise ValueError("Contenido demasiado grande")
        if path.is_dir():
            raise IsADirectoryError(rel)
        before = path.read_bytes() if path.exists() else None
        return self._make("write" if before is not None else "create", self.relpath(path), before, content, why)

    def propose_edit(self, rel: str, old: str, new: str, why: str) -> ProposedChange:
        path = self._writable(rel)
        if not path.is_file():
            raise FileNotFoundError(rel)
        text = path.read_text(encoding="utf-8")
        if not old:
            raise ValueError("El texto a reemplazar no puede estar vacío")
        n = text.count(old)
        if n != 1:
            raise ValueError(f"El texto a reemplazar debe aparecer exactamente una vez (apariciones: {n})")
        return self._make("write", self.relpath(path), text.encode(), text.replace(old, new, 1), why)

    def propose_delete(self, rel: str, why: str) -> ProposedChange:
        path = self._writable(rel)
        if not path.is_file():
            raise FileNotFoundError(rel)
        return self._make("delete", self.relpath(path), path.read_bytes(), None, why)

    # ---------- aplicación (requiere aprobación ligada)
    def apply(self, change: ProposedChange, approval: ApprovedAction) -> str:
        if approval.action_hash != change.proposal.action_hash:
            raise ConflictError("La aprobación no corresponde a este cambio")
        path = self._writable(change.rel)
        current = _sha(path.read_bytes()) if path.exists() else None
        if current != change.before_sha:
            raise ConflictError(f"{change.rel} cambió desde que se propuso la modificación")
        if change.kind == "delete":
            path.unlink()
            return f"Eliminado {change.rel}"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".axion-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(change.new_content or "")
            if path.exists():
                os.chmod(tmp, path.stat().st_mode & 0o777)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return f"{'Creado' if change.kind == 'create' else 'Modificado'} {change.rel}"
