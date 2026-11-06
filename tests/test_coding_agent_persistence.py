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
            UNIQUE(run_id, action_hash)
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
        gate.decide(run.pending[0].proposal_id, True, "reviewer")
        run = await agent.resume(run)

        self.assertEqual(run.status, "done")
        self.assertEqual(applied, ["src/file.py"])
        restored = agent.restore("run-1", "p1")
        self.assertEqual(restored.status, "done")
        self.assertEqual(restored.final, "Terminado")


if __name__ == "__main__":
    unittest.main()
