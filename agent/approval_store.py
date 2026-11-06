"""Aprobaciones persistentes. Estado y expiración se validan en la misma escritura atómica."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from agent.approval_gate import ActionProposal, ApprovalError, ApprovedAction
from rag.meta import MetaStore

COLS = "project_id, tool, what, why, resources, modification, risks, expected, fingerprint, action_hash, state, note, expires_at"


def _dt(v) -> datetime:
    d = datetime.fromisoformat(v) if isinstance(v, str) else v
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class DbApprovalGate:
    def __init__(self, meta: MetaStore, ttl_s: float = 900.0, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.meta, self.ttl_s, self.clock = meta, ttl_s, clock

    def request(self, proposal: ActionProposal) -> str:
        pid, now = uuid.uuid4().hex, self.clock()
        self.meta.execute(
            "INSERT INTO action_approvals (id, project_id, tool, what, why, resources, modification, risks, expected, fingerprint, "
            "action_hash, state, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (pid, proposal.project_id, proposal.tool, proposal.what, proposal.why, json.dumps(list(proposal.resources)),
             proposal.modification, json.dumps(list(proposal.risks)), proposal.expected, proposal.fingerprint,
             proposal.action_hash, now.isoformat(), (now + timedelta(seconds=self.ttl_s)).isoformat()))
        return pid

    def _row(self, pid) -> dict:
        rows = self.meta.query(f"SELECT {COLS} FROM action_approvals WHERE id = ?", (str(pid),))
        if not rows:
            raise ApprovalError(f"Aprobación inexistente: {pid}")
        return dict(zip(COLS.split(", "), rows[0]))

    def _expired(self, row) -> bool:
        return self.clock() >= _dt(row["expires_at"])

    def status(self, pid) -> tuple[str, str]:
        row = self._row(pid)
        if row["state"] in ("pending", "approved") and self._expired(row):
            return "expired", ""
        return row["state"], row["note"] or ""

    def decide(self, pid, approved: bool, reviewer: str, note: str = "") -> None:
        if not reviewer.strip():
            raise ApprovalError("Se requiere identificar al revisor")
        now = self.clock()
        new_state = "approved" if approved else "rejected"
        # La expiración y el estado se comprueban dentro del UPDATE, evitando la carrera TOCTOU.
        changed = self.meta.execute(
            "UPDATE action_approvals SET state = ?, reviewer = ?, note = ?, decided_at = ? "
            "WHERE id = ? AND state = 'pending' AND expires_at > ?",
            (new_state, reviewer, note, now.isoformat(), str(pid), now.isoformat()))
        if changed != 1:
            row = self._row(pid)
            if row["state"] != "pending":
                raise ApprovalError(f"La solicitud {pid} ya fue resuelta ({row['state']})")
            raise ApprovalError(f"La solicitud {pid} expiró")

    def redeem(self, pid, action_hash: str) -> ApprovedAction:
        rows = self.meta.query(
            "SELECT reviewer FROM action_approvals WHERE id = ? AND action_hash = ?",
            (str(pid), action_hash))
        if not rows:
            raise ApprovalError("La aprobación corresponde a otra acción o no existe")
        now = self.clock()
        changed = self.meta.execute(
            "UPDATE action_approvals SET state = 'used', used_at = ? "
            "WHERE id = ? AND state = 'approved' AND action_hash = ? AND expires_at > ?",
            (now.isoformat(), str(pid), action_hash, now.isoformat()))
        if changed != 1:
            state, _ = self.status(pid)
            raise ApprovalError(f"La aprobación no se puede canjear (estado: {state})")
        return ApprovedAction(pid, action_hash, rows[0][0] or "")

    def pending(self, project_id: str | None = None) -> list[tuple[str, ActionProposal]]:
        now = self.clock()
        sql = f"SELECT id, {COLS} FROM action_approvals WHERE state = 'pending' AND expires_at > ?"
        if project_id:
            sql += " AND project_id = ?"
        sql += " ORDER BY created_at"
        params = (now.isoformat(), project_id) if project_id else (now.isoformat(),)
        out = []
        for r in self.meta.query(sql, params):
            row = dict(zip(("id", *COLS.split(", ")), r))
            out.append((row["id"], ActionProposal(
                row["project_id"], row["tool"], row["what"], row["why"],
                tuple(json.loads(row["resources"])), row["modification"],
                tuple(json.loads(row["risks"])), row["expected"], row["fingerprint"])))
        return out
