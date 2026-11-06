import json
import sqlite3
import unittest

from rag.meta import MetaStore
from agent.run_store import RunStore, RunStoreError


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
        self.conn.execute("INSERT INTO projects(id) VALUES ('p1')")
        self.conn.execute("""CREATE TABLE agent_runs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, goal TEXT NOT NULL, status TEXT NOT NULL,
            final TEXT, error TEXT, messages TEXT NOT NULL, pending_actions TEXT NOT NULL,
            steps INTEGER NOT NULL, parse_failures INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        self.conn.execute("""CREATE TABLE agent_run_actions (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, project_id TEXT NOT NULL, tool TEXT NOT NULL,
            action_hash TEXT NOT NULL, args_json TEXT NOT NULL, proposal_id TEXT, summary TEXT NOT NULL,
            state TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(run_id, action_hash)
        )""")
        self.conn.commit()
        self.store = RunStore(MetaStore(self.conn), clock=lambda: "2026-01-01T00:00:00+00:00")

    def tearDown(self):
        self.conn.close()

    def test_run_snapshot_is_scoped_and_restorable(self):
        class Run:
            id, project_id, goal = "r1", "p1", "Revisar proyecto"
            status, final, error = "running", None, None
            messages, pending, steps, parse_failures = [{"role": "user", "content": "hola"}], [], 1, 0
        run = Run()
        self.store.create_run(run)
        self.store.save_run(run)
        saved = self.store.get_run("r1", "p1")
        self.assertEqual(saved["goal"], run.goal)
        self.assertEqual(saved["messages"], run.messages)
        with self.assertRaises(RunStoreError):
            self.store.get_run("r1", "otro-proyecto")

    def test_action_is_idempotent(self):
        class Run:
            id, project_id, goal = "r1", "p1", "Cambiar archivo"
            status, final, error = "running", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        self.store.create_run(Run())
        first = self.store.record_action("r1", "p1", "write_file", {"path": "a.py"}, "hash1", "approval1", "crear archivo")
        second = self.store.record_action("r1", "p1", "write_file", {"path": "a.py"}, "hash1", "approval2", "crear archivo")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["proposal_id"], "approval1")
        self.assertTrue(self.store.transition_action("r1", "hash1", ("pending",), "running"))
        self.assertFalse(self.store.transition_action("r1", "hash1", ("pending",), "running"))
        self.assertTrue(self.store.transition_action("r1", "hash1", ("running",), "applied"))
        self.assertFalse(self.store.transition_action("r1", "hash1", ("running",), "applied"))

    def test_running_action_is_not_claimed_twice(self):
        class Run:
            id, project_id, goal = "r1", "p1", "Ejecutar"
            status, final, error = "running", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        self.store.create_run(Run())
        self.store.record_action("r1", "p1", "run_command", {"command": "pytest"}, "hash2", "a2", "tests")
        self.assertTrue(self.store.transition_action("r1", "hash2", ("pending",), "running"))
        self.assertFalse(self.store.transition_action("r1", "hash2", ("pending", "approved"), "running"))


if __name__ == "__main__":
    unittest.main()
