"""Core Engine: orquesta Router + ContextManager + ModelManager para un turno de conversación
y agrega la salud de los componentes. No contiene lógica de herramientas ni de aprobaciones."""
import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from core.context import ContextManager
from core.models import GenerationResult, ModelManager
from core.router import ModelRouter, TaskKind
from core.tokens import estimate_messages, estimate_tokens

SUMMARY_SYSTEM = ("Resume la conversación técnica conservando decisiones, rutas de archivos, errores y tareas "
                  "pendientes. Responde solo con el resumen, en menos de 200 palabras.")


@dataclass
class Conversation:
    project_id: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    history: list[dict] = field(default_factory=list)
    summary: str = ""


class CoreEngine:
    def __init__(self, manager: ModelManager, router: ModelRouter, system_prompt: str,
                 context_tokens: int, reserve_output_tokens: int, keep_recent: int = 4,
                 health_checks: dict[str, Callable[[], Awaitable[bool]]] | None = None):
        self.manager, self.router, self.system_prompt = manager, router, system_prompt
        self.ctx = ContextManager(context_tokens, reserve_output_tokens, keep_recent, summarizer=self._summarize)
        self.health_checks = health_checks or {}

    async def _summarize(self, prior: str, older: list[dict]) -> str:
        body = ("Resumen previo:\n" + prior + "\n\n" if prior else "") + "\n".join(f"{m['role']}: {m['content']}" for m in older)
        decision = self.router.select(TaskKind.SUMMARY, estimate_tokens(body) + 200)
        res = await self.manager.generate(
            [{"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": body}],
            decision.model, decision.fallbacks)
        if res.incomplete or not res.text.strip():
            raise RuntimeError("resumen incompleto")
        return res.text.strip()

    async def _prepare(self, conv: Conversation, user_text: str, kind: TaskKind, extra_context: str, available: set[str] | None):
        history = conv.history + [{"role": "user", "content": user_text}]
        fit = await self.ctx.fit(self.system_prompt, history, conv.summary, extra_context)
        decision = self.router.select(kind, fit.estimated_tokens, available)
        return history, fit, decision

    def _commit(self, conv: Conversation, history: list[dict], fit, answer: str) -> None:
        conv.history = fit.recent + [{"role": "assistant", "content": answer}] if fit.summarized else history + [{"role": "assistant", "content": answer}]
        conv.summary = fit.summary

    async def respond(self, conv: Conversation, user_text: str, kind: TaskKind = TaskKind.CHAT,
                      extra_context: str = "", available: set[str] | None = None) -> tuple[GenerationResult, list[str]]:
        """Devuelve (resultado, advertencias). Si falla, la conversación queda intacta."""
        history, fit, decision = await self._prepare(conv, user_text, kind, extra_context, available)
        res = await self.manager.generate(fit.messages, decision.model, decision.fallbacks)
        warnings = list(decision.reasons)
        if fit.extra_truncated:
            warnings.append("El contexto recuperado se truncó por falta de espacio")
        if fit.summarizer_failed:
            warnings.append("El resumen del historial usó el respaldo determinista")
        if res.incomplete:
            warnings.append(f"Respuesta incompleta: {res.incomplete}")
        if res.uncertain:
            warnings.append("El modelo expresó incertidumbre: verificar antes de aplicar")
        self._commit(conv, history, fit, res.text)
        return res, warnings

    async def respond_stream(self, conv: Conversation, user_text: str, kind: TaskKind = TaskKind.CHAT,
                             extra_context: str = "", available: set[str] | None = None):
        history, fit, decision = await self._prepare(conv, user_text, kind, extra_context, available)
        parts: list[str] = []
        async for piece in self.manager.stream(fit.messages, decision.model):
            parts.append(piece)
            yield piece
        self._commit(conv, history, fit, "".join(parts))

    async def health(self, timeout_s: float = 5.0) -> dict[str, bool]:
        async def one(check):
            try:
                return bool(await asyncio.wait_for(check(), timeout_s))
            except Exception:  # noqa: BLE001
                return False
        names = list(self.health_checks)
        results = await asyncio.gather(*(one(self.health_checks[n]) for n in names))
        return dict(zip(names, results))
