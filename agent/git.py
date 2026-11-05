"""Git Manager: lectura libre (con redacción de secretos) y cambios al repositorio solo mediante propuestas
aprobables. Sin operaciones de red (push/pull/fetch/clone). Hooks desactivados al confirmar."""
import hashlib
import re
import subprocess

from agent.approval_gate import ActionProposal, ApprovedAction
from agent.secrets import SENSITIVE_GLOBS, is_sensitive_path, redact
from agent.workspace import AccessDenied, ConflictError, Workspace
from core.errors import AxionError

REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
MAX_OUT = 20000
EXCLUDES = [f":(exclude,glob)**/{g}" for g in SENSITIVE_GLOBS if not g.endswith(".*")] + [":(exclude,glob)**/.env.*"]


class GitError(AxionError):
    code = "git_error"


class GitManager:
    def __init__(self, ws: Workspace, timeout_s: int = 30):
        self.ws, self.timeout_s = ws, timeout_s

    def _run(self, args: list[str], extra_c: list[str] | None = None) -> str:
        cmd = ["git", "-C", str(self.ws.root), "-c", "core.hooksPath=/dev/null", "-c", "core.pager=cat", *(extra_c or []), *args]
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "HOME": "/nonexistent"}
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_s, env=env, check=False)
        except subprocess.TimeoutExpired as exc:
            raise GitError("git excedió el tiempo límite") from exc
        except FileNotFoundError as exc:
            raise GitError("git no está instalado") from exc
        if p.returncode != 0:
            raise GitError(redact((p.stderr or p.stdout).strip())[:500])
        return p.stdout

    def _clip(self, s: str) -> str:
        s = redact(s)
        return s if len(s) <= MAX_OUT else s[:MAX_OUT] + "\n…(salida truncada)"

    # ---------- lectura
    def is_repo(self) -> bool:
        try:
            return self._run(["rev-parse", "--is-inside-work-tree"]).strip() == "true"
        except GitError:
            return False

    def head(self) -> str | None:
        try:
            return self._run(["rev-parse", "--short", "HEAD"]).strip() or None
        except GitError:
            return None

    def status(self) -> str:
        return self._clip(self._run(["status", "--porcelain=v1", "--branch"]))

    def diff(self, path: str | None = None, staged: bool = False) -> str:
        args = ["diff", "--no-color"] + (["--cached"] if staged else []) + ["--"]
        if path:
            rel = self.ws.relpath(self.ws.resolve(path))
            if is_sensitive_path(rel):
                raise AccessDenied(f"Acceso denegado: {rel}")
            args.append(rel)
        else:
            args.append(".")
        return self._clip(self._run(args + EXCLUDES))

    def log(self, limit: int = 10) -> str:
        n = max(1, min(int(limit), 50))
        return self._clip(self._run(["log", f"-{n}", "--date=short", "--format=%h %ad %an: %s"]))

    # ---------- cambios (propuestas)
    def _paths(self, paths: list[str]) -> list[str]:
        if not paths:
            raise ValueError("Indica al menos un archivo")
        out = []
        for p in paths:
            rel = self.ws.relpath(self.ws.resolve(p))
            if is_sensitive_path(rel) or rel == ".git" or rel.startswith(".git/"):
                raise AccessDenied(f"No se puede confirmar: {rel}")
            out.append(rel)
        return sorted(set(out))

    def _fingerprint(self, message: str, rels: list[str]) -> str:
        parts = [message]
        for r in rels:
            f = self.ws.root / r
            parts.append(f"{r}:{hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else 'absent'}")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def propose_commit(self, message: str, paths: list[str], why: str) -> ActionProposal:
        message = message.strip()
        if not message or len(message) > 500 or "\0" in message:
            raise ValueError("Mensaje de commit inválido")
        rels = self._paths(paths)
        shown = self._run(["diff", "--no-color", "HEAD", "--", *rels]) if self._has_head() else "(repositorio sin commits)"
        return ActionProposal(self.ws.project_id, "git.commit", f"git commit: {message}", why, tuple(rels),
                              self._clip(shown), ("Crea un commit en la rama actual", "Archivos nuevos se añaden al índice"),
                              "Un commit nuevo con solo los archivos indicados", self._fingerprint(message, rels))

    def _has_head(self) -> bool:
        try:
            self._run(["rev-parse", "--verify", "HEAD"]); return True
        except GitError:
            return False

    def apply_commit(self, message: str, paths: list[str], proposal: ActionProposal, approval: ApprovedAction) -> str:
        if approval.action_hash != proposal.action_hash:
            raise ConflictError("La aprobación no corresponde a este commit")
        message, rels = message.strip(), self._paths(paths)
        if self._fingerprint(message, rels) != proposal.fingerprint:
            raise ConflictError("Los archivos cambiaron desde que se propuso el commit")
        ident = []
        for key, default in (("user.name", "Axion Atomic"), ("user.email", "axion-atomic@localhost")):
            try:
                if not self._run(["config", "--get", key]).strip():
                    raise GitError("")
            except GitError:
                ident += ["-c", f"{key}={default}"]
        self._run(["add", "--", *rels])
        self._run(["commit", "-m", message, "--only", "--", *rels], extra_c=ident)
        return "Commit creado: " + self._run(["log", "-1", "--format=%h %s"]).strip()

    def propose_create_branch(self, name: str, why: str) -> ActionProposal:
        if not REF_RE.match(name) or ".." in name or name.endswith((".lock", "/")):
            raise ValueError("Nombre de rama inválido")
        return ActionProposal(self.ws.project_id, "git.branch", f"crear y cambiar a la rama {name}", why, (name,),
                              f"git switch -c {name}", ("Cambia la rama activa",), f"La rama {name} queda activa",
                              hashlib.sha256(f"branch|{name}".encode()).hexdigest())

    def apply_create_branch(self, name: str, proposal: ActionProposal, approval: ApprovedAction) -> str:
        if approval.action_hash != proposal.action_hash:
            raise ConflictError("La aprobación no corresponde a esta acción")
        self._run(["switch", "-c", name])
        return f"Rama activa: {name}"
