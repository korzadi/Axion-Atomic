"""Aprobaciones ligadas a una acción concreta. Una aprobación se canjea UNA vez y solo si el hash
de la acción coincide con el aprobado. Implementación en memoria (un proceso); DbApprovalGate proporciona la variante persistente en PostgreSQL."""
import hashlib
import itertools
import json
import time
from dataclasses import dataclass, field
from typing import Callable

from core.errors import AxionError


class ApprovalError(AxionError):
    code = "approval_error"


@dataclass(frozen=True)
class ActionProposal:
    project_id: str
    tool: str
    what: str
    why: str
    resources: tuple[str, ...]
    modification: str            # diff o comando propuesto, tal como lo verá el revisor
    risks: tuple[str, ...]
    expected: str
    fingerprint: str             # identifica el contenido exacto de la acción (p. ej. hash del nuevo contenido)

    @property
    def action_hash(self) -> str:
        blob = json.dumps([self.project_id, self.tool, sorted(self.resources), self.fingerprint], ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()


@dataclass(frozen=True)
class ApprovedAction:
    proposal_id: int | str
    action_hash: str
    reviewer: str


@dataclass
class Record:
    proposal: ActionProposal
    created: float
    state: str = "pending"       # pending | approved | rejected | used
    reviewer: str = ""
    note: str = ""


class InMemoryApprovalGate:
    def __init__(self, ttl_s: float = 900.0, clock: Callable[[], float] = time.monotonic):
        self.ttl_s, self.clock = ttl_s, clock
        self._records: dict[int, Record] = {}
        self._ids = itertools.count(1)

    def request(self, proposal: ActionProposal) -> int:
        pid = next(self._ids)
        self._records[pid] = Record(proposal, self.clock())
        return pid

    def _get(self, pid: int) -> Record:
        try:
            return self._records[pid]
        except KeyError:
            raise ApprovalError(f"Aprobación inexistente: {pid}") from None

    def decide(self, pid: int, approved: bool, reviewer: str, note: str = "") -> None:
        rec = self._get(pid)
        if rec.state != "pending":
            raise ApprovalError(f"La solicitud {pid} ya fue resuelta ({rec.state})")
        if self.clock() - rec.created > self.ttl_s:
            raise ApprovalError(f"La solicitud {pid} expiró")
        if not reviewer.strip():
            raise ApprovalError("Se requiere identificar al revisor")
        rec.state, rec.reviewer, rec.note = ("approved" if approved else "rejected"), reviewer, note

    def status(self, pid: int) -> tuple[str, str]:
        rec = self._get(pid)
        if rec.state in ("pending", "approved") and self.clock() - rec.created > self.ttl_s:
            return "expired", ""
        return rec.state, rec.note

    def pending(self) -> list[tuple[int, ActionProposal]]:
        return [(i, r.proposal) for i, r in self._records.items() if r.state == "pending" and self.status(i)[0] == "pending"]

    def redeem(self, pid: int, action_hash: str) -> ApprovedAction:
        rec = self._get(pid)
        state, _ = self.status(pid)
        if state != "approved":
            raise ApprovalError(f"La solicitud {pid} no está aprobada (estado: {state})")
        if rec.proposal.action_hash != action_hash:
            raise ApprovalError("La aprobación corresponde a otra acción")
        rec.state = "used"
        return ApprovedAction(pid, action_hash, rec.reviewer)
