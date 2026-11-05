"""Aprobaciones persistentes (PostgreSQL/SQLite vía MetaStore). Misma interfaz que InMemoryApprovalGate.
El canje es atómico entre procesos: UPDATE ... WHERE state='approved' AND action_hash=? (rowcount == 1)."""
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
        return self.clock() > _dt(row["expires_at"])

    def status(self, pid) -> tuple[str, str]:
        row = self._row(pid)
        if row["state"] in ("pending", "approved") and self._expired(row):
            return "expired", ""
        return row["state"], row["note"] or ""

    def decide(self, pid, approved: bool, reviewer: str, note: str = "") -> None:
        row = self._row(pid)
        if row["state"] != "pending":
            raise ApprovalError(f"La solicitud {pid} ya fue resuelta ({row['state']})")
        if self._expired(row):
            raise ApprovalError(f"La solicitud {pid} expiró")
        if not reviewer.strip():
            raise ApprovalError("Se requiere identificar al revisor")
        n = self.meta.execute("UPDATE action_approvals SET state = ?, reviewer = ?, note = ?, decided_at = ? WHERE id = ? AND state = 'pending'",
                              ("approved" if approved else "rejected", reviewer, note, self.clock().isoformat(), str(pid)))
        if n != 1:
            raise ApprovalError(f"La solicitud {pid} fue resuelta por otro revisor")

    def redeem(self, pid, action_hash: str) -> ApprovedAction:
        row = self._row(pid)
        state, _ = self.status(pid)
        if state != "approved":
            raise ApprovalError(f"La solicitud {pid} no está aprobada (estado: {state})")
        if row["action_hash"] != action_hash:
            raise ApprovalError("La aprobación corresponde a otra acción")
        n = self.meta.execute("UPDATE action_approvals SET state = 'used', used_at = ? WHERE id = ? AND state = 'approved' AND action_hash = ?",
                              (self.clock().isoformat(), str(pid), action_hash))
        if n != 1:
            raise ApprovalError(f"La aprobación {pid} ya fue utilizada")
        reviewer = self.meta.query("SELECT reviewer FROM action_approvals WHERE id = ?", (str(pid),))[0][0]
        return ApprovedAction(pid, action_hash, reviewer or "")

    def pending(self, project_id: str | None = None) -> list[tuple[str, ActionProposal]]:
        sql = f"SELECT id, {COLS} FROM action_approvals WHERE state = 'pending'" + (" AND project_id = ?" if project_id else "") + " ORDER BY created_at"
        out = []
        for r in self.meta.query(sql, (project_id,) if project_id else ()):
            row = dict(zip(("id", *COLS.split(", ")), r))
            if self._expired(row):
                continue
            out.append((row["id"], ActionProposal(row["project_id"], row["tool"], row["what"], row["why"], tuple(json.loads(row["resources"])),
                                                  row["modification"], tuple(json.loads(row["risks"])), row["expected"], row["fingerprint"])))
        return out
