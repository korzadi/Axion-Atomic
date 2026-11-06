"""Persistencia de ejecuciones y acciones idempotentes del agente AXION."""
import json
import uuid
from datetime import datetime, timezone

from core.errors import AxionError
from agent.secrets import find_secrets, redact
from rag.meta import MetaStore


class RunStoreError(AxionError):
    code = "run_store_error"


def _now():
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """Almacena snapshots y evita volver a aplicar la misma acción dentro de un proyecto.

    Una acción que quedó en estado 'running' tras una interrupción no se reejecuta
    automáticamente: requiere reconciliación humana porque el efecto externo podría
    haberse producido antes de caer el proceso.
    """

    def __init__(self, meta: MetaStore, clock=_now):
        self.meta, self.clock = meta, clock

    def create_run(self, run):
        now = self.clock()
        self.meta.execute(
            "INSERT INTO agent_runs (id, project_id, goal, status, final, error, messages, pending_actions, "
            "steps, parse_failures, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run.id, run.project_id, redact(run.goal), run.status, run.final, run.error,
             redact(json.dumps(run.messages, ensure_ascii=False)), "[]", run.steps, run.parse_failures, now, now),
        )

    def save_run(self, run):
        now = self.clock()
        pending = [
            {"proposal_id": str(p.proposal_id), "tool": p.tool, "args": p.args,
             "action_hash": p.action_hash, "summary": p.summary, "action_run_id": p.action_run_id or run.id}
            for p in run.pending
        ]
        pending_json = json.dumps(pending, ensure_ascii=False)
        if find_secrets(pending_json):
            raise RunStoreError("La acción pendiente contiene patrones de secretos; no se persistió")
        changed = self.meta.execute(
            "UPDATE agent_runs SET status = ?, final = ?, error = ?, messages = ?, pending_actions = ?, "
            "steps = ?, parse_failures = ?, updated_at = ? WHERE id = ? AND project_id = ?",
            (run.status, redact(run.final) if run.final else None, redact(run.error) if run.error else None,
             redact(json.dumps(run.messages, ensure_ascii=False)), redact(pending_json), run.steps, run.parse_failures, now, run.id, run.project_id),
        )
        if changed != 1:
            raise RunStoreError("No se pudo guardar la ejecución o no pertenece al proyecto indicado")

    def get_run(self, run_id: str, project_id: str) -> dict:
        rows = self.meta.query(
            "SELECT id, project_id, goal, status, final, error, messages, pending_actions, steps, "
            "parse_failures, created_at, updated_at FROM agent_runs WHERE id = ? AND project_id = ?",
            (run_id, project_id),
        )
        if not rows:
            raise RunStoreError("Ejecución inexistente o fuera del proyecto autorizado")
        row = rows[0]
        return dict(zip(
            ("id", "project_id", "goal", "status", "final", "error", "messages", "pending_actions",
             "steps", "parse_failures", "created_at", "updated_at"), row
        )) | {
            "messages": json.loads(row[6]),
            "pending_actions": json.loads(row[7]),
        }

    def record_action(self, run_id: str, project_id: str, tool: str, args: dict,
                      action_hash: str, proposal_id: str, summary: str) -> dict:
        self.get_run(run_id, project_id)
        args_json = json.dumps(args, sort_keys=True, ensure_ascii=False)
        if find_secrets(args_json):
            raise RunStoreError("La carga útil de la acción contiene patrones de secretos; no se persistió")
        now = self.clock()
        self.meta.execute(
            "INSERT INTO agent_run_actions (id, run_id, project_id, tool, action_hash, args_json, "
            "proposal_id, summary, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?) "
            "ON CONFLICT (project_id, action_hash) DO NOTHING",
            (uuid.uuid4().hex, run_id, project_id, tool, action_hash,
             args_json, str(proposal_id), redact(summary), now, now),
        )
        row = self.get_project_action(project_id, action_hash)
        if row["tool"] != tool or row["args_json"] != args_json:
            raise RunStoreError("Conflicto de idempotencia: el hash coincide con otra carga útil")
        return row

    def get_action(self, run_id: str, action_hash: str) -> dict | None:
        rows = self.meta.query(
            "SELECT id, run_id, project_id, tool, action_hash, args_json, proposal_id, summary, state, result "
            "FROM agent_run_actions WHERE run_id = ? AND action_hash = ?",
            (run_id, action_hash),
        )
        return self._action_row(rows)

    def get_project_action(self, project_id: str, action_hash: str) -> dict | None:
        rows = self.meta.query(
            "SELECT id, run_id, project_id, tool, action_hash, args_json, proposal_id, summary, state, result "
            "FROM agent_run_actions WHERE project_id = ? AND action_hash = ?",
            (project_id, action_hash),
        )
        return self._action_row(rows)

    @staticmethod
    def _action_row(rows):
        if not rows:
            return None
        return dict(zip(("id", "run_id", "project_id", "tool", "action_hash", "args_json",
                         "proposal_id", "summary", "state", "result"), rows[0]))

    def transition_action(self, run_id: str, action_hash: str, expected: tuple[str, ...],
                          new_state: str, result: str | None = None) -> bool:
        if not expected:
            raise ValueError("Se requiere al menos un estado de origen")
        marks = ",".join("?" for _ in expected)
        changed = self.meta.execute(
            f"UPDATE agent_run_actions SET state = ?, result = ?, updated_at = ? "
            f"WHERE run_id = ? AND action_hash = ? AND state IN ({marks})",
            (new_state, redact(result) if result else None, self.clock(), run_id, action_hash, *expected),
        )
        return changed == 1
