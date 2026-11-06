"""Gestión de contexto: ajusta system + historial al presupuesto de tokens y resume lo antiguo."""
from dataclasses import dataclass
from typing import Awaitable, Callable

from core.errors import ContextOverflow
from core.tokens import estimate_messages, estimate_tokens

Summarizer = Callable[[str, list[dict]], Awaitable[str]]  # (resumen_previo, mensajes_antiguos) -> resumen


@dataclass
class FitResult:
    messages: list[dict]
    recent: list[dict]          # historial que se conserva literal
    summary: str                # resumen vigente (vacío si no hizo falta)
    estimated_tokens: int
    summarized: bool = False
    extra_truncated: bool = False
    summarizer_failed: bool = False


def digest(messages: list[dict], per_msg: int = 160) -> str:
    """Resumen determinista de respaldo (sin modelo)."""
    lines = []
    for m in messages:
        text = " ".join(m["content"].split())
        lines.append(f"- {m['role']}: {text[:per_msg]}{'…' if len(text) > per_msg else ''}")
    return "\n".join(lines)


class ContextManager:
    def __init__(self, max_context_tokens: int, reserve_output_tokens: int, keep_recent: int = 4,
                 summary_max_tokens: int = 600, summarizer: Summarizer | None = None):
        if reserve_output_tokens >= max_context_tokens:
            raise ValueError("reserve_output_tokens debe ser menor que max_context_tokens")
        self.budget = max_context_tokens - reserve_output_tokens
        self.keep_recent = keep_recent
        self.summary_max_chars = int(summary_max_tokens * 3.2)
        self.summarizer = summarizer

    async def fit(self, system: str, history: list[dict], prior_summary: str = "", extra_context: str = "") -> FitResult:
        extra_truncated = False
        max_extra_chars = int(self.budget * 0.4 * 3.2)
        if len(extra_context) > max_extra_chars:
            extra_context, extra_truncated = extra_context[:max_extra_chars], True
        system_text = system + (("\n\n" + extra_context) if extra_context else "")

        def build(summary: str, recent: list[dict]) -> list[dict]:
            msgs = [{"role": "system", "content": system_text}]
            if summary:
                msgs.append({"role": "system", "content": "Resumen de la conversación anterior:\n" + summary})
            return msgs + recent

        msgs = build(prior_summary, history)
        if estimate_messages(msgs) <= self.budget:
            return FitResult(msgs, history, prior_summary, estimate_messages(msgs), extra_truncated=extra_truncated)
        if not history:
            raise ContextOverflow("El contexto del sistema por sí solo excede el presupuesto")

        recent = list(history[-self.keep_recent:])
        older = history[:-self.keep_recent] if len(history) > self.keep_recent else []
        summary, failed = prior_summary, False
        if older:
            try:
                if self.summarizer is None:
                    raise RuntimeError("sin summarizer")
                summary = await self.summarizer(prior_summary, older)
            except Exception:  # noqa: BLE001  el respaldo determinista evita perder el hilo
                failed = True
                summary = (prior_summary + "\n" if prior_summary else "") + digest(older)
            summary = summary[-self.summary_max_chars:]
        # si aún no cabe, sacar mensajes antiguos de "recent" hacia el resumen, sin tocar el último
        while estimate_messages(build(summary, recent)) > self.budget and len(recent) > 1:
            moved = recent.pop(0)
            summary = (summary + "\n" + digest([moved]))[-self.summary_max_chars:]
            failed = failed or self.summarizer is None
        final = build(summary, recent)
        if estimate_messages(final) > self.budget:
            raise ContextOverflow(
                f"El último mensaje (~{estimate_tokens(recent[-1]['content'])} tokens) no cabe en el presupuesto de {self.budget}; divide la tarea")
        return FitResult(final, recent, summary, estimate_messages(final), True, extra_truncated, failed)
