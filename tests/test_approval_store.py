import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from agent.approval_gate import ActionProposal, ApprovalError
from agent.approval_store import DbApprovalGate
from rag.meta import MetaStore


class DbApprovalGateTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
        self.conn.execute("INSERT INTO projects(id) VALUES ('p1')")
        self.conn.execute("""CREATE TABLE action_approvals (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, tool TEXT NOT NULL, what TEXT NOT NULL,
            why TEXT NOT NULL, resources TEXT NOT NULL, modification TEXT NOT NULL, risks TEXT NOT NULL,
            expected TEXT NOT NULL, fingerprint TEXT NOT NULL, action_hash TEXT NOT NULL,
            state TEXT NOT NULL, reviewer TEXT, note TEXT, created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL, decided_at TEXT, used_at TEXT
        )""")
        self.conn.commit()
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.gate = DbApprovalGate(MetaStore(self.conn), ttl_s=900, clock=lambda: self.now)
        self.proposal = ActionProposal("p1", "write_file", "Crear archivo", "Implementar cambio",
                                       ("src/a.py",), "diff", ("riesgo bajo",), "archivo creado", "fp-1")

    def tearDown(self):
        self.conn.close()

    def test_approval_is_bound_and_redeemed_once(self):
        pid = self.gate.request(self.proposal)
        self.assertEqual(self.gate.status(pid)[0], "pending")
        self.gate.decide(pid, True, "reviewer", "revisado")
        self.assertEqual(self.gate.status(pid), ("approved", "revisado"))
        redeemed = self.gate.redeem(pid, self.proposal.action_hash)
        self.assertEqual(redeemed.action_hash, self.proposal.action_hash)
        self.assertEqual(self.gate.status(pid)[0], "used")
        with self.assertRaises(ApprovalError):
            self.gate.redeem(pid, self.proposal.action_hash)

    def test_wrong_action_hash_cannot_redeem(self):
        pid = self.gate.request(self.proposal)
        self.gate.decide(pid, True, "reviewer")
        with self.assertRaises(ApprovalError):
            self.gate.redeem(pid, "wrong-hash")

    def test_rejected_approval_cannot_be_redeemed(self):
        pid = self.gate.request(self.proposal)
        self.gate.decide(pid, False, "reviewer", "No autorizado")
        self.assertEqual(self.gate.status(pid), ("rejected", "No autorizado"))
        with self.assertRaises(ApprovalError):
            self.gate.redeem(pid, self.proposal.action_hash)
        self.assertEqual(self.gate.status(pid)[0], "rejected")

    def test_expired_approval_cannot_be_decided_or_redeemed(self):
        pid = self.gate.request(self.proposal)
        self.now += timedelta(seconds=901)
        self.assertEqual(self.gate.status(pid)[0], "expired")
        with self.assertRaises(ApprovalError):
            self.gate.decide(pid, True, "reviewer")
        with self.assertRaises(ApprovalError):
            self.gate.redeem(pid, self.proposal.action_hash)


if __name__ == "__main__":
    unittest.main()
