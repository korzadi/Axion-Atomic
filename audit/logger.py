"""Audit Logger: registro append-only con cadena de hashes (detecta alteraciones, no las impide: la protección
de escritura corresponde a los permisos de la base de datos). Redacta secretos y claves sensibles antes de guardar."""
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Callable

from agent.secrets import redact
from core.errors import AxionError
from rag.meta import MetaStore

SENSITIVE_KEY = re.compile(r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|private|credential)", re.I)
MAX_JSON = 8000


class AuditConflict(AxionError):
    code = "audit_conflict"


def clean(obj, depth: int = 0):
    if depth > 6:
        return "[...]"
    if isinstance(obj, dict):
        return {str(k)[:100]: ("[REDACTED]" if SENSITIVE_KEY.search(str(k)) else clean(v, depth + 1)) for k, v in list(obj.items())[:50]}
    if isinstance(obj, (list, tuple)):
        return [clean(v, depth + 1) for v in list(obj)[:50]]
    if isinstance(obj, str):
        return redact(obj)[:2000]
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    return str(obj)[:200]


def _hash(prev: str, seq: int, ts: str, project: str | None, actor: str, event: str, data: str) -> str:
    return hashlib.sha256("|".join([prev, str(seq), ts, project or "", actor, event, data]).encode()).hexdigest()


class AuditLogger:
    def __init__(self, meta: MetaStore, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), max_retries: int = 20):
        self.meta, self.clock, self.max_retries = meta, clock, max_retries

    def log(self, event: str, actor: str, project_id: str | None, data: dict | None = None) -> int:
        text = json.dumps(clean(data or {}), sort_keys=True, ensure_ascii=False)
        if len(text) > MAX_JSON:
            text = json.dumps({"truncated": True, "preview": text[:2000]}, ensure_ascii=False)
        for _ in range(self.max_retries):
            seq0, last = self.meta.query("SELECT seq, last_hash FROM audit_chain_head WHERE id = 1")[0]
            seq, ts = seq0 + 1, self.clock().isoformat()
            h = _hash(last, seq, ts, project_id, actor, event[:100], text)
            try:
                with self.meta.transaction() as cur:
                    cur.execute(self.meta.sql("UPDATE audit_chain_head SET last_hash = ?, seq = ? WHERE id = 1 AND seq = ?"), (h, seq, seq0))
                    if cur.rowcount != 1:
                        raise AuditConflict("cadena avanzada por otro proceso")
                    cur.execute(self.meta.sql("INSERT INTO audit_log (seq, ts, project_id, actor, event, data, prev_hash, hash) "
                                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"), (seq, ts, project_id, actor, event[:100], text, last, h))
                return seq
            except AuditConflict:
                continue
        raise AuditConflict("No se pudo registrar el evento de auditoría tras varios intentos")

    def hook(self, project_id: str | None, actor: str) -> Callable[[dict], None]:
        """Adaptador para on_event del agente y del sandbox."""
        return lambda e: self.log(str(e.get("type", "event")), actor, project_id, e)

    def verify(self) -> tuple[bool, int | None]:
        rows = self.meta.query("SELECT seq, ts, project_id, actor, event, data, prev_hash, hash FROM audit_log ORDER BY seq")
        prev, expect = "", 1
        for seq, ts, project, actor, event, data, prev_hash, h in rows:
            ts = ts if isinstance(ts, str) else ts.isoformat()
            if seq != expect or prev_hash != prev or _hash(prev, seq, ts, project, actor, event, data) != h:
                return False, seq
            prev, expect = h, seq + 1
        head_seq, head_hash = self.meta.query("SELECT seq, last_hash FROM audit_chain_head WHERE id = 1")[0]
        if head_seq != expect - 1 or head_hash != prev:
            return False, head_seq                        # registros finales eliminados
        return True, None

    def tail(self, project_id: str | None = None, limit: int = 50) -> list[dict]:
        sql = "SELECT seq, ts, project_id, actor, event, data FROM audit_log" + (" WHERE project_id = ?" if project_id else "") + " ORDER BY seq DESC LIMIT ?"
        rows = self.meta.query(sql, ((project_id,) if project_id else ()) + (min(limit, 500),))
        return [{"seq": r[0], "ts": str(r[1]), "project_id": r[2], "actor": r[3], "event": r[4], "data": json.loads(r[5])} for r in rows]
