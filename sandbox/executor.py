"""Terminal Executor + Test Runner. Ejecuta SIEMPRE sobre una copia temporal del proyecto, mediante el backend.
auto -> se ejecuta; approval -> propuesta ligada al comando exacto; blocked -> error."""
import asyncio
import hashlib
import json
from typing import Callable

from agent.approval_gate import ActionProposal, ApprovedAction
from agent.diagnostics import TestSummary, parse_diagnostics, parse_test_output, render_diagnostics
from agent.secrets import redact
from agent.workspace import Workspace
from core.errors import AxionError
from sandbox.backends import ResourceLimits
from sandbox.policy import CommandBlocked, Decision, NeedsApproval, classify
from sandbox.runner import ExecResult
from sandbox.snapshot import Snapshot


class NoTestsDetected(AxionError):
    code = "no_tests_detected"


def render_result(res: ExecResult, limit: int = 6000) -> str:
    head = "TIEMPO AGOTADO: el comando se detuvo" if res.timed_out else f"código de salida: {res.exit_code}"
    parts = [f"{head} ({res.duration_s:.1f}s)" + (" [salida truncada]" if res.truncated else "")]
    for label, text in (("stdout", res.stdout), ("stderr", res.stderr)):
        if text.strip():
            parts.append(f"--- {label} ---\n{redact(text)[-limit:]}")
    diags = parse_diagnostics(res.stdout + "\n" + res.stderr, roots=("/workspace/",))
    if diags and res.exit_code != 0:
        parts.append("--- diagnósticos ---\n" + render_diagnostics(diags[:15]))
    return "\n".join(parts)


def detect_test_command(ws: Workspace) -> tuple[str, list[str]]:
    r = ws.root
    def has(*names): return any((r / n).exists() for n in names)
    def text(n): return (r / n).read_text("utf-8", "replace") if (r / n).is_file() else ""
    if has("pytest.ini", "conftest.py", "tox.ini") or "pytest" in text("pyproject.toml") or "pytest" in text("requirements.txt"):
        return "pytest", ["python", "-m", "pytest", "-q"]
    if has("go.mod"):
        return "go", ["go", "test", "./..."]
    if has("Cargo.toml"):
        return "cargo", ["cargo", "test"]
    if has("package.json"):
        try:
            if "test" in json.loads(text("package.json")).get("scripts", {}):
                return "npm", ["npm", "test"]
        except ValueError:
            pass
    if has("tests", "test") or any(r.glob("test_*.py")):
        return "unittest", ["python", "-m", "unittest", "discover"]
    raise NoTestsDetected("No se detectó un framework de pruebas conocido")


class SandboxExecutor:
    def __init__(self, backend, ws: Workspace, limits: ResourceLimits | None = None, audit: Callable[[dict], None] | None = None,
                 snapshot_dir: str | None = None):
        self.backend, self.ws, self.limits = backend, ws, limits or ResourceLimits()
        self.audit, self.snapshot_dir = audit or (lambda e: None), snapshot_dir

    def _execute(self, argv: list[str], network: bool, approval_id) -> ExecResult:
        with Snapshot(self.ws, base_dir=self.snapshot_dir) as snap:
            res = self.backend.run(argv, str(snap), self.limits, network)
            res.stdout, res.stderr = res.stdout.replace(str(snap), "/workspace"), res.stderr.replace(str(snap), "/workspace")
        self.audit({"type": "sandbox_run", "project": self.ws.project_id, "command": redact(" ".join(argv))[:300], "network": network,
                    "exit_code": res.exit_code, "timed_out": res.timed_out, "duration_s": round(res.duration_s, 2),
                    "backend": res.backend, "approval_id": approval_id})
        return res

    async def run_auto(self, command: str) -> ExecResult:
        d = classify(command)
        if d.level == "blocked":
            raise CommandBlocked("; ".join(d.reasons))
        if d.level == "approval":
            raise NeedsApproval("Este comando requiere aprobación: " + "; ".join(d.reasons), d)
        return await asyncio.to_thread(self._execute, d.argv, False, None)

    async def run_tests(self) -> tuple[ExecResult, TestSummary | None]:
        framework, argv = detect_test_command(self.ws)
        res = await asyncio.to_thread(self._execute, argv, False, None)
        try:
            summary = parse_test_output("unittest" if framework == "unittest" else framework, res.stdout + "\n" + res.stderr) \
                if framework in ("unittest", "pytest", "go", "cargo") else None
        except ValueError:
            summary = None
        return res, summary

    # ---- ejecución con aprobación (instalaciones, red, comandos desconocidos)
    def propose(self, command: str, why: str) -> tuple[ActionProposal, Decision]:
        d = classify(command)
        if d.level == "blocked":
            raise CommandBlocked("; ".join(d.reasons))
        risks = list(d.reasons) + (["Acceso a la red habilitado para esta ejecución"] if d.network else [])
        risks.append("Se ejecuta en una copia temporal del proyecto: no modifica tus archivos")
        fp = hashlib.sha256(json.dumps([d.argv, d.network]).encode()).hexdigest()
        return ActionProposal(self.ws.project_id, "sandbox.run", f"Ejecutar en el sandbox: {' '.join(d.argv)}"[:200], why,
                              ("(copia temporal del proyecto)",), " ".join(d.argv), tuple(risks),
                              "El comando corre aislado y se informa su salida", fp), d

    async def apply(self, d: Decision, approval: ApprovedAction) -> ExecResult:
        return await asyncio.to_thread(self._execute, d.argv, d.network, approval.proposal_id)
