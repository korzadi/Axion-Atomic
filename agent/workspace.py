"""File Manager: acceso confinado a un directorio de proyecto. Lectura libre (con redacción de secretos),
escritura solo mediante propuestas que requieren una aprobación ligada al hash exacto del cambio."""
import difflib
import errno
import hashlib
import os
import stat
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


def _relative_parts(rel: str) -> list[str]:
    if not isinstance(rel, str) or not rel or "\0" in rel or "\\" in rel:
        raise PathViolation("Ruta relativa inválida")
    if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise PathViolation("Se requieren rutas relativas al proyecto")
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PathViolation("Ruta relativa inválida")
    return parts


def _open_parent(root: Path, rel: str, create: bool = False) -> tuple[int, str]:
    """Abre cada directorio por descriptor y sin seguir symlinks."""
    parts = _relative_parts(rel)
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise PathViolation("El sistema no admite apertura segura sin symlinks")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(root, flags)
    try:
        for part in parts[:-1]:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o700, dir_fd=fd)
                next_fd = os.open(part, flags, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise PathViolation("No se permiten symlinks ni componentes que no sean directorios") from None
                raise
            os.close(fd)
            fd = next_fd
        return fd, parts[-1]
    except Exception:
        os.close(fd)
        raise


def _read_regular_at(parent_fd: int, leaf: str, limit: int | None = None) -> bytes:
    """Lee un archivo regular relativo a un descriptor de directorio, sin seguir symlinks."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(leaf, flags, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise PathViolation("No se permiten symlinks ni archivos especiales") from None
        raise
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise AccessDenied("Solo se permiten archivos regulares")
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if limit is not None and total > limit:
                raise AccessDenied(f"Archivo mayor que {limit} bytes")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _open_directory(root: Path, rel: str = ".") -> int:
    """Abre un directorio y todos sus ancestros sin seguir symlinks."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    if rel == ".":
        return os.open(root, flags)
    parts = _relative_parts(rel)
    fd = os.open(root, flags)
    try:
        for part in parts:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise PathViolation("No se permiten symlinks ni componentes que no sean directorios") from None
                raise
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _read_regular(root: Path, rel: str, limit: int | None = None) -> bytes:
    parent_fd, leaf = _open_parent(root, rel)
    try:
        return _read_regular_at(parent_fd, leaf, limit)
    finally:
        os.close(parent_fd)

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
        try:
            # Incluso las lecturas parciales respetan el límite total de memoria.
            raw = _read_regular(self.root, rel, self.max_read_bytes)
        except FileNotFoundError:
            raise FileNotFoundError(rel) from None
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
        fd = _open_directory(self.root, rel)
        try:
            out = []
            for name in sorted(os.listdir(fd)):
                r = name if rel == "." else f"{rel}/{name}"
                try:
                    st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    # El elemento desapareció durante la enumeración: omitirlo.
                    continue
                if stat.S_ISLNK(st.st_mode) or not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                    continue
                is_dir = stat.S_ISDIR(st.st_mode)
                if is_sensitive_path(r) or self.ignore.is_ignored(r, is_dir):
                    continue
                out.append({"name": name, "type": "dir" if is_dir else "file",
                            "size": st.st_size if stat.S_ISREG(st.st_mode) else None})
            return out
        finally:
            os.close(fd)

    def walk(self, max_files: int = 5000) -> Iterator[str]:
        if max_files <= 0:
            return
        count = 0

        def visit(dir_fd: int, prefix: str):
            nonlocal count
            try:
                names = sorted(os.listdir(dir_fd))
            except OSError:
                return
            for name in names:
                if count >= max_files:
                    return
                rel = f"{prefix}/{name}" if prefix else name
                try:
                    st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if stat.S_ISLNK(st.st_mode):
                    continue
                if stat.S_ISDIR(st.st_mode):
                    if is_sensitive_path(rel + "/x") or self.ignore.is_ignored(rel, True):
                        continue
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
                    try:
                        child_fd = os.open(name, flags, dir_fd=dir_fd)
                    except (FileNotFoundError, NotADirectoryError, OSError):
                        continue
                    try:
                        yield from visit(child_fd, rel)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(st.st_mode):
                    if is_sensitive_path(rel) or self.ignore.is_ignored(rel, False):
                        continue
                    count += 1
                    yield rel

        root_fd = _open_directory(self.root, ".")
        try:
            yield from visit(root_fd, "")
        finally:
            os.close(root_fd)

    def search(self, query: str, glob: str | None = None, max_results: int = 50, case_sensitive: bool = False) -> list[dict]:
        if not query:
            raise ValueError("Consulta vacía")
        needle = query if case_sensitive else query.lower()
        out = []
        for rel in self.walk():
            if glob and not Path(rel).match(glob):
                continue
            try:
                raw = _read_regular(self.root, rel, self.max_read_bytes)
            except (FileNotFoundError, PathViolation, AccessDenied):
                # Nunca seguir un reemplazo por symlink ni leer archivos especiales.
                continue
            if b"\0" in raw[:8192]:
                continue
            for no, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
                if needle in (line if case_sensitive else line.lower()):
                    out.append({"path": rel, "line": no, "text": redact(line.strip())[:200]})
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
        try:
            before = _read_regular(self.root, rel, MAX_WRITE_BYTES)
        except FileNotFoundError:
            before = None
        return self._make("write" if before is not None else "create", self.relpath(path), before, content, why)

    def propose_edit(self, rel: str, old: str, new: str, why: str) -> ProposedChange:
        path = self._writable(rel)
        if not path.is_file():
            raise FileNotFoundError(rel)
        text = _read_regular(self.root, rel, MAX_WRITE_BYTES).decode("utf-8")
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
        return self._make("delete", self.relpath(path), _read_regular(self.root, rel, MAX_WRITE_BYTES), None, why)

    # ---------- aplicación (requiere aprobación ligada)
    def apply(self, change: ProposedChange, approval: ApprovedAction) -> str:
        if approval.action_hash != change.proposal.action_hash:
            raise ConflictError("La aprobación no corresponde a este cambio")
        path = self._writable(change.rel)
        try:
            current_bytes = _read_regular(self.root, change.rel, MAX_WRITE_BYTES)
        except FileNotFoundError:
            current_bytes = None
        current = _sha(current_bytes) if current_bytes is not None else None
        if current != change.before_sha:
            raise ConflictError(f"{change.rel} cambió desde que se propuso la modificación")
        parent_fd, leaf = _open_parent(self.root, change.rel, create=True)
        tmp_name = f".axion-{os.getpid()}-{hashlib.sha256(os.urandom(16)).hexdigest()[:16]}"
        try:
            # Revalidar el hash usando el mismo descriptor de directorio que se
            # utilizará para replace/unlink; no confiar en una lectura previa por ruta.
            try:
                current_at_parent = _read_regular_at(parent_fd, leaf, MAX_WRITE_BYTES)
            except FileNotFoundError:
                current_at_parent = None
            current_sha = _sha(current_at_parent) if current_at_parent is not None else None
            if current_sha != change.before_sha:
                raise ConflictError(f"{change.rel} cambió antes de aplicar la modificación")
            try:
                existing = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                if not stat.S_ISREG(existing.st_mode):
                    raise AccessDenied("El destino dejó de ser un archivo regular")
                mode = existing.st_mode & 0o777
            except FileNotFoundError:
                if change.before_sha is not None:
                    raise ConflictError(f"{change.rel} desapareció antes de aplicar la modificación")
                mode = 0o600
            if change.kind == "delete":
                # Comprobación final del tipo; el directorio padre permanece abierto.
                os.unlink(leaf, dir_fd=parent_fd)
                return f"Eliminado {change.rel}"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            fd = os.open(tmp_name, flags, mode, dir_fd=parent_fd)
            try:
                data = (change.new_content or "").encode("utf-8")
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp_name, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            return f"{'Creado' if change.kind == 'create' else 'Modificado'} {change.rel}"
        finally:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)
