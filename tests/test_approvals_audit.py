import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.approval_gate import ActionProposal, ApprovalError
from agent.approval_store import DbApprovalGate
from audit.logger import AuditLogger
from tests.rag_helpers import make_meta, open_meta

FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


def prop(project="p1", fp="f1", tool="fs.write"):
    return ActionProposal(project, tool, "escribir a.txt", "porque sí", ("a.txt",), "+hola", ("riesgo1",), "queda escrito", fp)


class Clock:
    def __init__(self): self.t = datetime(2026, 11, 5, tzinfo=timezone.utc)
    def __call__(self): return self.t
    def advance(self, **kw): self.t += timedelta(**kw)


class DbGateTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.meta = make_meta()
        self.gate = DbApprovalGate(self.meta, ttl_s=100, clock=self.clock)

    def test_full_flow_single_use_and_bound_to_hash(self):
        p = prop(); pid = self.gate.request(p)
        self.assertEqual(self.gate.status(pid)[0], "pending")
        with self.assertRaises(ApprovalError): self.gate.redeem(pid, p.action_hash)
        self.gate.decide(pid, True, "ana")
        with self.assertRaises(ApprovalError): self.gate.redeem(pid, "otro")
        ap = self.gate.redeem(pid, p.action_hash)
        self.assertEqual((ap.reviewer, ap.action_hash), ("ana", p.action_hash))
        with self.assertRaises(ApprovalError): self.gate.redeem(pid, p.action_hash)
        self.assertEqual(self.gate.status(pid)[0], "used")

    def test_survives_restart_and_pending_rebuilds_proposal(self):
        p = prop(); pid = self.gate.request(p)
        new_gate = DbApprovalGate(self.meta, ttl_s=100, clock=self.clock)            # "reinicio": otra instancia, misma base
        ((got_id, got),) = new_gate.pending("p1")
        self.assertEqual((got_id, got.action_hash, got.resources, got.risks), (pid, p.action_hash, ("a.txt",), ("riesgo1",)))
        self.assertEqual(new_gate.pending("p2"), [])

    def test_reject_expire_and_validation(self):
        pid = self.gate.request(prop()); self.gate.decide(pid, False, "ana", "no")
        self.assertEqual(self.gate.status(pid), ("rejected", "no"))
        with self.assertRaises(ApprovalError): self.gate.decide(pid, True, "ana")
        pid2 = self.gate.request(prop(fp="f2"))
        with self.assertRaises(ApprovalError): self.gate.decide(pid2, True, "  ")
        self.clock.advance(seconds=500)
        self.assertEqual(self.gate.status(pid2)[0], "expired")
        with self.assertRaises(ApprovalError): self.gate.decide(pid2, True, "ana")
        self.assertEqual(self.gate.pending(), [])
        with self.assertRaises(ApprovalError): self.gate.status("no-existe")

    def test_approved_but_expired_cannot_be_redeemed(self):
        p = prop(); pid = self.gate.request(p); self.gate.decide(pid, True, "ana"); self.clock.advance(seconds=500)
        with self.assertRaises(ApprovalError): self.gate.redeem(pid, p.action_hash)

    def test_concurrent_redeem_only_one_wins(self):
        p = prop(); pid = self.gate.request(p); self.gate.decide(pid, True, "ana")
        results, barrier = [], threading.Barrier(8)
        def go():
            barrier.wait()
            try: self.gate.redeem(pid, p.action_hash); results.append("ok")
            except ApprovalError: results.append("fail")
        ts = [threading.Thread(target=go) for _ in range(8)]; [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(results.count("ok"), 1)

    def test_unknown_project_rejected_by_foreign_key(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError): self.gate.request(prop(project="no-existe"))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.meta = make_meta(); self.clock = Clock(); self.log = AuditLogger(self.meta, self.clock)

    def test_chain_verifies_and_orders(self):
        for i in range(5): self.clock.advance(seconds=1); self.assertEqual(self.log.log("evento", "ana", "p1", {"i": i}), i + 1)
        self.assertEqual(self.log.verify(), (True, None))
        self.assertEqual([r["seq"] for r in self.log.tail("p1", 3)], [5, 4, 3])
        self.assertEqual(AuditLogger(make_meta()).verify(), (True, None))                  # cadena vacía válida

    def test_tampering_is_detected(self):
        for i in range(4): self.log.log("e", "ana", "p1", {"i": i})
        self.meta.execute("UPDATE audit_log SET data = ? WHERE seq = 2", ('{"i": 99}',))
        self.assertEqual(self.log.verify(), (False, 2))
        self.meta.execute("UPDATE audit_log SET data = ? WHERE seq = 2", (json.dumps({"i": 1}, sort_keys=True),))
        self.assertEqual(self.log.verify(), (True, None))
        self.meta.execute("DELETE FROM audit_log WHERE seq = 4")                              # truncar el final
        self.assertFalse(self.log.verify()[0])
        self.meta.execute("DELETE FROM audit_log WHERE seq = 2")                              # hueco en medio
        self.assertFalse(self.log.verify()[0])

    def test_redaction_and_size_cap(self):
        self.log.log("x", "ana", "p1", {"password": "hunter2hunter2", "api_key": "k", "nota": f'clave "{FAKE_AWS}"',
                                        "anidado": {"token": "t", "ok": 1}, "lista": [f"{FAKE_AWS}"]})
        stored = json.dumps(self.log.tail()[0]["data"])
        for leaked in ("hunter2", FAKE_AWS, '"t"'): self.assertNotIn(leaked, stored)
        self.assertIn("[REDACTED]", stored); self.assertIn('"ok": 1', stored)
        self.log.log("big", "ana", None, {f"k{i}": "x" * 1500 for i in range(30)})
        self.assertTrue(self.log.tail()[0]["data"]["truncated"]); self.assertTrue(self.log.verify()[0])

    def test_two_connections_write_concurrently_without_forking_chain(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "audit.db"); m1 = make_meta(db_path=path); m2 = open_meta(path)
            a, b = AuditLogger(m1), AuditLogger(m2); errors = []
            def work(lg, name):
                try:
                    for i in range(20): lg.log("e", name, "p1", {"i": i})
                except Exception as exc: errors.append(exc)
            ts = [threading.Thread(target=work, args=(a, "a")), threading.Thread(target=work, args=(b, "b"))]
            [t.start() for t in ts]; [t.join() for t in ts]
            self.assertEqual(errors, [])
            seqs = [r[0] for r in m1.query("SELECT seq FROM audit_log ORDER BY seq")]
            self.assertEqual(seqs, list(range(1, 41))); self.assertEqual(a.verify(), (True, None))

    def test_hook_adapter(self):
        self.log.hook("p1", "agente")({"type": "tool_call", "tool": "read_file", "step": 1})
        r = self.log.tail()[0]; self.assertEqual((r["event"], r["actor"], r["data"]["tool"]), ("tool_call", "agente", "read_file"))


if __name__ == "__main__":
    unittest.main()
