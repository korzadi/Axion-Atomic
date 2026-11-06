import sqlite3
import unittest

from agent.approval_gate import ActionProposal, InMemoryApprovalGate
from agent.coding_agent import CodingAgent
from agent.toolset import Tool
from rag.meta import MetaStore
from agent.run_store import RunStore


class CodingAgentPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_and_repeated_action_do_not_apply_twice(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO projects(id) VALUES ('p1')")
        conn.execute("""CREATE TABLE agent_runs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, goal TEXT NOT NULL, status TEXT NOT NULL,
            final TEXT, error TEXT, messages TEXT NOT NULL, pending_actions TEXT NOT NULL,
            steps INTEGER NOT NULL, parse_failures INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE agent_run_actions (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, project_id TEXT NOT NULL, tool TEXT NOT NULL,
            action_hash TEXT NOT NULL, args_json TEXT NOT NULL, proposal_id TEXT, summary TEXT NOT NULL,
            state TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(project_id, action_hash)
        )""")
        conn.commit()

        applied = []
        gate = InMemoryApprovalGate()
        proposal = ActionProposal("p1", "change", "Cambiar archivo", "Corregir defecto",
                                 ("src/file.py",), "diff", (), "archivo corregido", "fingerprint-v1")
        tool = Tool("change", "cambio controlado", {"path": ("str", True)},
                    propose=lambda args: (proposal, lambda approval: applied.append(args["path"]) or "ok"))
        answers = iter([
            '{"tool":"change","args":{"path":"src/file.py"}}',
            '{"tool":"change","args":{"path":"src/file.py"}}',
            '{"final":"Terminado"}',
        ])
        async def chat(_messages):
            return next(answers)

        agent = CodingAgent(chat, {"change": tool}, gate, run_store=RunStore(MetaStore(conn)))
        run = await agent.run("Reparar", project_id="p1", run_id="run-1")
        self.assertEqual(run.status, "awaiting_approval")
        restored_pending = agent.restore("run-1", "p1")
        self.assertEqual(restored_pending.status, "awaiting_approval")
        gate.decide(restored_pending.pending[0].proposal_id, True, "reviewer")
        run = await agent.resume(restored_pending)

        self.assertEqual(run.status, "done")
        self.assertEqual(applied, ["src/file.py"])
        restored = agent.restore("run-1", "p1")
        self.assertEqual(restored.status, "done")
        self.assertEqual(restored.final, "Terminado")

        second_answers = iter([
            '{"tool":"change","args":{"path":"src/file.py"}}',
            '{"final":"Ya estaba aplicado"}',
        ])
        async def second_chat(_messages):
            return next(second_answers)
        second_agent = CodingAgent(second_chat, {"change": tool}, gate, run_store=agent.run_store)
        second_run = await second_agent.run("Revisar cambio", project_id="p1", run_id="run-2")
        self.assertEqual(second_run.status, "done")
        self.assertEqual(applied, ["src/file.py"])


    async def test_restore_marks_interrupted_running_action_for_reconciliation(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO projects(id) VALUES ('p1')")
        conn.execute("""CREATE TABLE agent_runs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, goal TEXT NOT NULL, status TEXT NOT NULL,
            final TEXT, error TEXT, messages TEXT NOT NULL, pending_actions TEXT NOT NULL,
            steps INTEGER NOT NULL, parse_failures INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE agent_run_actions (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, project_id TEXT NOT NULL, tool TEXT NOT NULL,
            action_hash TEXT NOT NULL, args_json TEXT NOT NULL, proposal_id TEXT, summary TEXT NOT NULL,
            state TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(project_id, action_hash)
        )""")
        conn.commit()

        from agent.coding_agent import AgentRun, PendingAction

        store = RunStore(MetaStore(conn))
        run = AgentRun(
            goal="Aplicar un cambio",
            messages=[{"role": "user", "content": "Aplicar un cambio"}],
            id="interrupted-run",
            project_id="p1",
            status="awaiting_approval",
            pending=[PendingAction("approval-1", "change", {"path": "src/a.py"},
                                   "action-hash-1", "Actualizar archivo", "interrupted-run")],
        )
        store.create_run(run)
        store.record_action(
            "interrupted-run", "p1", "change", {"path": "src/a.py"},
            "action-hash-1", "approval-1", "Actualizar archivo",
        )
        self.assertTrue(store.transition_action(
            "interrupted-run", "action-hash-1", ("pending",), "running"
        ))
        store.save_run(run)

        async def unexpected_chat(_messages):
            raise AssertionError("Una acción interrumpida no debe reanudar el modelo automáticamente")

        agent = CodingAgent(unexpected_chat, {}, InMemoryApprovalGate(), run_store=store)
        restored = agent.restore("interrupted-run", "p1")

        self.assertEqual(restored.status, "needs_reconciliation")
        self.assertIn("reconciliación humana", restored.error)
        self.assertEqual(store.get_project_action("p1", "action-hash-1")["state"], "running")


if __name__ == "__main__":
    unittest.main()
