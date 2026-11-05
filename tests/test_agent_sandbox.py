"""Integración: agente + herramientas del sandbox + aprobaciones persistentes + auditoría + memoria.
El modelo está guionizado (no se mide aquí su calidad); todo lo demás se ejecuta de verdad."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.approval_store import DbApprovalGate
from agent.coding_agent import CodingAgent
from agent.git import GitManager
from agent.toolset import build_tools
from agent.workspace import Workspace
from audit.logger import AuditLogger
from rag.memory import MemoryManager
from sandbox.backends import LocalBackend, ResourceLimits
from sandbox.executor import SandboxExecutor
from tests.rag_helpers import make_meta


def act(tool, **a): return json.dumps({"tool": tool, "args": a})
def fin(t): return json.dumps({"final": t})


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"AXION_ALLOW_UNSAFE_LOCAL_SANDBOX": "1"}); p.start(); self.addCleanup(p.stop)
        self.tmp, self.sbx = tempfile.TemporaryDirectory(), tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.sbx.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "app.py").write_text("def add(a, b):\n    return a - b\n")
        (self.root / "test_app.py").write_text("import unittest\nfrom app import add\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2, 3), 5)\n")
        self.meta = make_meta(); self.audit = AuditLogger(self.meta); self.gate = DbApprovalGate(self.meta)
        self.ws = Workspace(self.root, "p1")
        self.events = []
        def hook(e): self.events.append(e); self.audit.hook("p1", "agente")(e)
        self.sandbox = SandboxExecutor(LocalBackend(), self.ws, ResourceLimits(), audit=hook, snapshot_dir=self.sbx.name)
        self.tools = build_tools(self.ws, GitManager(self.ws), self.sandbox)
        self.hook = hook

    def agent(self, replies):
        replies, self.seen = list(replies), []
        async def chat(msgs): self.seen.append([m["content"] for m in msgs]); return replies.pop(0)
        return CodingAgent(chat, self.tools, self.gate, on_event=self.hook)

    async def test_fix_bug_verify_with_tests_end_to_end(self):
        a = self.agent([act("run_tests"), act("edit_file", path="app.py", old="a - b", new="a + b", reason="la suma resta"),
                        act("run_tests"), fin("Corregido y verificado")])
        run = await a.run("arregla add y verifica")
        self.assertEqual(run.status, "awaiting_approval")
        self.assertTrue(any("0 ok, 1 fallidas" in m for m in self.seen[1]))              # el agente VIO el fallo real
        self.assertIn("a - b", (self.root / "app.py").read_text())
        ((pid, proposal),) = self.gate.pending("p1"); self.gate.decide(pid, True, "ana")
        run = await a.resume(run)
        self.assertEqual((run.status, run.final), ("done", "Corregido y verificado"))
        self.assertTrue(any("1 ok, 0 fallidas" in m for m in self.seen[-1]))              # y VERIFICÓ la corrección
        self.assertIn("a + b", (self.root / "app.py").read_text())
        self.assertEqual(os.listdir(self.sbx.name), [])
        ok, bad = self.audit.verify(); self.assertTrue(ok, bad)
        kinds = [r["event"] for r in reversed(self.audit.tail("p1", 50))]
        for needed in ("sandbox_run", "approval_requested", "approval_result", "final"): self.assertIn(needed, kinds)
        mem = MemoryManager(self.meta)
        recorded = [await mem.record_from_event("p1", e) for e in self.events]
        self.assertEqual(len([r for r in recorded if r]), 1)                               # solo la modificación aplicada

    async def test_install_needs_approval_and_rejection_runs_nothing(self):
        a = self.agent([act("run_sandboxed", command="pip install requests"),
                        act("run_command_approved", command="pip install requests", reason="necesito la librería"), fin("sin instalar")])
        run = await a.run("instala requests")
        self.assertTrue(any("run_command_approved" in m and "aprobación" in m for m in self.seen[1]))
        self.assertEqual(run.status, "awaiting_approval")
        ((pid, prop),) = self.gate.pending("p1")
        self.assertTrue(any("red" in r.lower() for r in prop.risks))
        self.gate.decide(pid, False, "ana", "sin red")
        run = await a.resume(run)
        self.assertEqual(run.status, "done")
        self.assertEqual([e for e in self.events if e["type"] == "sandbox_run"], [])      # nada se ejecutó

    async def test_approved_command_runs_in_sandbox_and_is_not_recorded_as_modification(self):
        a = self.agent([act("run_command_approved", command="bash -c 'echo hola-sandbox'", reason="probar"), fin("listo")])
        run = await a.run("g"); self.gate.decide(run.pending[0].proposal_id, True, "ana")
        run = await a.resume(run)
        self.assertTrue(any("EJECUTADO" in m and "hola-sandbox" in m for m in self.seen[1]))
        mem = MemoryManager(self.meta)
        self.assertEqual([await mem.record_from_event("p1", e) for e in self.events if e["type"] == "approval_result"], [None])

    async def test_blocked_command_is_reported_to_model(self):
        a = self.agent([act("run_sandboxed", command="sudo rm -rf /"), act("run_sandboxed", command="cat /etc/passwd"), fin("ok")])
        run = await a.run("g"); self.assertEqual(run.status, "done")
        joined = "\n".join(self.seen[-1]); self.assertIn("prohibido", joined); self.assertIn("fuera del proyecto", joined)
        self.assertEqual([e for e in self.events if e["type"] == "sandbox_run"], [])

    async def test_tools_listed_in_prompt_only_when_sandbox_enabled(self):
        a = self.agent([fin("x")]); await a.run("g")
        self.assertIn("run_tests", self.seen[0][0])
        self.assertNotIn("run_tests", build_tools(self.ws, GitManager(self.ws)))


if __name__ == "__main__":
    unittest.main()
