import json
import sqlite3
import unittest

from rag.meta import MetaStore
from agent.run_store import RunNotFoundError, RunStore, RunStoreError


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
            UNIQUE(project_id, action_hash)
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
        with self.assertRaises(RunNotFoundError):
            self.store.get_run("inexistente", "p1")

    def test_cancelled_run_cannot_be_overwritten_by_a_late_snapshot(self):
        class Run:
            id, project_id, goal = "r-cancel", "p1", "Cancelar"
            status, final, error = "awaiting_approval", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        run = Run()
        self.store.create_run(run)
        self.store.meta.execute(
            "UPDATE agent_runs SET status='cancelled' WHERE id='r-cancel'"
        )
        run.status = "running"
        with self.assertRaisesRegex(RunStoreError, "cancelada"):
            self.store.save_run(run)
        self.assertEqual(self.store.get_run("r-cancel", "p1")["status"], "cancelled")

    def test_cancelled_run_cannot_record_new_actions(self):
        class Run:
            id, project_id, goal = "r-cancel-action", "p1", "Cancelar"
            status, final, error = "awaiting_approval", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        self.store.create_run(Run())
        self.store.meta.execute(
            "UPDATE agent_runs SET status='cancelled' WHERE id='r-cancel-action'"
        )
        with self.assertRaisesRegex(RunStoreError, "cancelada"):
            self.store.record_action("r-cancel-action", "p1", "write_file",
                                     {"path": "a.py"}, "hash-cancel", "approval", "crear")
        self.assertIsNone(self.store.get_project_action("p1", "hash-cancel"))

    def test_cancellation_between_check_and_insert_is_atomic(self):
        class Run:
            id, project_id, goal = "r-cancel-race", "p1", "Carrera"
            status, final, error = "awaiting_approval", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        self.store.create_run(Run())
        original = self.store.get_run
        calls = {"n": 0}

        def stale_read(run_id, project_id):
            row = original(run_id, project_id)
            calls["n"] += 1
            if calls["n"] == 1:
                self.store.meta.execute(
                    "UPDATE agent_runs SET status='cancelled' WHERE id=:i",
                    {"i": run_id},
                )
            return row

        self.store.get_run = stale_read
        with self.assertRaisesRegex(RunStoreError, "cancelada"):
            self.store.record_action("r-cancel-race", "p1", "write_file",
                                     {"path": "a.py"}, "hash-race", "approval", "crear")
        self.assertIsNone(self.store.get_project_action("p1", "hash-race"))

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

    def test_same_action_is_deduplicated_across_runs_in_one_project(self):
        class Run:
            status, final, error = "running", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        first_run = Run()
        first_run.id, first_run.project_id, first_run.goal = "r1", "p1", "primera"
        second_run = Run()
        second_run.id, second_run.project_id, second_run.goal = "r2", "p1", "segunda"
        self.store.create_run(first_run)
        self.store.create_run(second_run)
        first = self.store.record_action("r1", "p1", "write_file", {"path": "a.py"}, "same-hash", "approval-1", "crear")
        second = self.store.record_action("r2", "p1", "write_file", {"path": "a.py"}, "same-hash", "approval-2", "crear")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.store.get_project_action("p1", "same-hash")["run_id"], "r1")


    def test_secrets_are_not_persisted_in_goals_or_action_payloads(self):
        fake_key = "AKIAABCDEFGHIJKLMNOP"
        class Run:
            id, project_id = "r-secret", "p1"
            goal = "Revisar " + fake_key
            status, final, error = "running", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        run = Run()
        self.store.create_run(run)
        saved = self.store.get_run("r-secret", "p1")
        self.assertNotIn(fake_key, saved["goal"])
        with self.assertRaises(RunStoreError):
            self.store.record_action("r-secret", "p1", "write_file",
                                     {"content": fake_key}, "secret-hash", "approval", "no guardar")


    def test_same_hash_with_different_payload_is_rejected(self):
        class Run:
            id, project_id, goal = "r-conflict", "p1", "Conflicto"
            status, final, error = "running", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        self.store.create_run(Run())
        self.store.record_action("r-conflict", "p1", "write_file", {"path": "a.py"},
                                 "same-hash", "approval-1", "crear")
        with self.assertRaises(RunStoreError):
            self.store.record_action("r-conflict", "p1", "write_file", {"path": "b.py"},
                                     "same-hash", "approval-2", "crear otro")

    def test_idempotency_key_is_scoped_to_project(self):
        self.conn.execute("INSERT INTO projects(id) VALUES ('p2')")
        self.conn.commit()
        class Run:
            status, final, error = "running", None, None
            messages, pending, steps, parse_failures = [], [], 0, 0
        one, two = Run(), Run()
        one.id, one.project_id, one.goal = "r-p1", "p1", "acción p1"
        two.id, two.project_id, two.goal = "r-p2", "p2", "acción p2"
        self.store.create_run(one)
        self.store.create_run(two)
        self.store.record_action("r-p1", "p1", "write_file", {"path": "a.py"}, "same-hash", "a1", "crear")
        self.store.record_action("r-p2", "p2", "write_file", {"path": "a.py"}, "same-hash", "a2", "crear")
        self.assertEqual(self.store.get_project_action("p1", "same-hash")["run_id"], "r-p1")
        self.assertEqual(self.store.get_project_action("p2", "same-hash")["run_id"], "r-p2")

if __name__ == "__main__":
    unittest.main()
