"""Memory Manager: memoria persistente por proyecto (arquitectura, decisiones, modificaciones, notas).
Aislada por project_id; los secretos se redactan antes de guardar; retención configurable."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from agent.secrets import redact
from rag.lexical import bm25_rank, query_terms
from rag.meta import MetaStore

KINDS = ("architecture", "decision", "modification", "note")
SOURCES = ("agent", "user", "system")
MAX_TEXT = 2000


class MemoryManager:
    def __init__(self, meta: MetaStore, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.meta, self.clock = meta, clock

    async def record(self, project_id: str, kind: str, text: str, source: str = "agent") -> str:
        if not project_id:
            raise ValueError("project_id es obligatorio")
        if kind not in KINDS or source not in SOURCES:
            raise ValueError("Tipo o fuente de memoria inválidos")
        text = redact(text.strip())
        if not text:
            raise ValueError("Memoria vacía")
        mid = uuid.uuid4().hex
        await asyncio.to_thread(self.meta.add_memory, mid, project_id, kind, text[:MAX_TEXT], source, self.clock().isoformat())
        return mid

    async def recall(self, project_id: str, query: str = "", limit: int = 5) -> list[dict]:
        rows = await asyncio.to_thread(self.meta.list_memories, project_id, 200)      # ya ordenadas: más recientes primero
        if not query.strip():
            return rows[:limit]
        ranked = bm25_rank(query_terms(query), [(r["id"], r["text"]) for r in rows])
        by_id = {r["id"]: r for r in rows}
        return [by_id[i] for i, _ in ranked[:limit]]

    async def summary(self, project_id: str, max_items: int = 10) -> str:
        rows = [r for r in await asyncio.to_thread(self.meta.list_memories, project_id, 200) if r["kind"] in ("architecture", "decision")]
        return "\n".join(f"- [{r['kind']}] {r['text']}" for r in rows[:max_items])

    async def forget(self, project_id: str, memory_id: str) -> bool:
        return await asyncio.to_thread(self.meta.delete_memory, project_id, memory_id)

    async def purge_older_than(self, project_id: str, days: int) -> int:
        if days < 1:
            raise ValueError("days debe ser >= 1")
        cutoff = (self.clock() - timedelta(days=days)).isoformat()
        return await asyncio.to_thread(self.meta.purge_memories_before, project_id, cutoff)

    async def record_from_event(self, project_id: str, event: dict) -> str | None:
        """Adaptador para on_event del agente: registra solo modificaciones realmente aplicadas."""
        if event.get("type") == "approval_result" and str(event.get("result", "")).startswith("APLICADO"):
            return await self.record(project_id, "modification", f"{event.get('tool')}: {event['result']}", "agent")
        return None
