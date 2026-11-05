"""Model Manager: configuración, reintentos, detección de respuestas incompletas/inciertas,
fallback entre modelos, límites de memoria y métricas. Independiente del transporte HTTP."""
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable, Protocol

from core.errors import ModelConfigError, ModelUnavailable, TransportError


@dataclass(frozen=True)
class ModelConfig:
    name: str
    num_ctx: int = 8192
    temperature: float = 0.2
    top_p: float = 0.9
    max_output_tokens: int = 2048
    keep_alive: str = "10m"
    est_memory_gb: float = 6.0  # estimación declarada por el operador; no se mide automáticamente

    def options(self) -> dict:
        return {"temperature": self.temperature, "top_p": self.top_p,
                "num_ctx": self.num_ctx, "num_predict": self.max_output_tokens}


@dataclass
class ChatResponse:
    content: str
    finish_reason: str = "stop"  # "length" = cortada por límite de tokens
    prompt_tokens: int = 0
    completion_tokens: int = 0


class Transport(Protocol):
    async def chat(self, model: str, messages: list[dict], options: dict, keep_alive: str) -> ChatResponse: ...
    def chat_stream(self, model: str, messages: list[dict], options: dict, keep_alive: str) -> AsyncIterator[str]: ...
    async def list_models(self) -> set[str]: ...


@dataclass
class GenerationResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"
    latency_s: float = 0.0
    attempts: int = 1
    continuations: int = 0
    fallback_used: bool = False
    incomplete: str | None = None   # motivo si la respuesta sigue incompleta
    uncertain: bool = False         # el modelo expresó incertidumbre (señal débil, no garantía)


UNCERTAINTY_MARKERS = (
    "no estoy seguro", "no estoy segura", "no puedo garantizar", "no tengo suficiente información",
    "no tengo acceso a", "i'm not sure", "i am not sure", "i cannot guarantee", "i don't have enough information",
    "i may be wrong", "puede que me equivoque",
)


def detect_uncertainty(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in UNCERTAINTY_MARKERS)


def detect_incomplete(text: str, finish_reason: str, expect_json: bool = False) -> str | None:
    if finish_reason == "length":
        return "length"
    if text.count("```") % 2 == 1:
        return "unclosed_code_fence"
    if expect_json:
        try:
            json.loads(text)
        except ValueError:
            return "invalid_json"
    if not text.strip():
        return "empty"
    return None


CONTINUE_PROMPT = "Continúa exactamente donde te quedaste, sin repetir lo ya escrito."


class ModelManager:
    def __init__(self, transport: Transport, memory_budget_gb: float = 9.0, max_retries: int = 2,
                 backoff_s: float = 0.5, max_continuations: int = 2,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.transport = transport
        self.memory_budget_gb = memory_budget_gb
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.max_continuations = max_continuations
        self._sleep = sleep
        self._models: dict[str, ModelConfig] = {}
        self.stats = {"requests": 0, "retries": 0, "failures": 0, "fallbacks": 0,
                      "prompt_tokens": 0, "completion_tokens": 0}

    # --- registro y límites de memoria
    def register(self, cfg: ModelConfig) -> None:
        if cfg.est_memory_gb > self.memory_budget_gb:
            raise ModelConfigError(f"{cfg.name} requiere ~{cfg.est_memory_gb} GB y el presupuesto es {self.memory_budget_gb} GB")
        if not 0 <= cfg.temperature <= 2 or cfg.num_ctx < 512 or cfg.max_output_tokens < 1:
            raise ModelConfigError(f"Parámetros inválidos para {cfg.name}")
        if cfg.max_output_tokens >= cfg.num_ctx:
            raise ModelConfigError("max_output_tokens debe ser menor que num_ctx")
        self._models[cfg.name] = cfg

    def get(self, name: str) -> ModelConfig:
        try:
            return self._models[name]
        except KeyError:
            raise ModelConfigError(f"Modelo no registrado: {name}") from None

    def registered(self) -> list[ModelConfig]:
        return list(self._models.values())

    # --- generación
    async def _call_with_retries(self, cfg: ModelConfig, messages: list[dict]) -> tuple[ChatResponse, int]:
        last: TransportError | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                return await self.transport.chat(cfg.name, messages, cfg.options(), cfg.keep_alive), attempt
            except TransportError as exc:
                last = exc
                if not exc.retryable or attempt > self.max_retries:
                    break
                self.stats["retries"] += 1
                await self._sleep(self.backoff_s * (2 ** (attempt - 1)))
        assert last is not None
        raise last

    async def generate(self, messages: list[dict], model: str, fallbacks: list[str] | None = None,
                       expect_json: bool = False) -> GenerationResult:
        errors: list[str] = []
        chain = [model] + [m for m in (fallbacks or []) if m != model]
        for idx, name in enumerate(chain):
            cfg = self.get(name)
            started = time.monotonic()
            self.stats["requests"] += 1
            try:
                resp, attempts = await self._call_with_retries(cfg, messages)
            except TransportError as exc:
                self.stats["failures"] += 1
                errors.append(f"{name}: {exc}")
                continue
            text, ptok, ctok, reason = resp.content, resp.prompt_tokens, resp.completion_tokens, resp.finish_reason
            continuations = 0
            while continuations < self.max_continuations and detect_incomplete(text, reason) in ("length", "unclosed_code_fence"):
                convo = messages + [{"role": "assistant", "content": text}, {"role": "user", "content": CONTINUE_PROMPT}]
                try:
                    more, _ = await self._call_with_retries(cfg, convo)
                except TransportError as exc:
                    errors.append(f"{name} (continuación): {exc}")
                    break
                text += more.content
                ptok += more.prompt_tokens
                ctok += more.completion_tokens
                reason = more.finish_reason
                continuations += 1
            if idx > 0:
                self.stats["fallbacks"] += 1
            self.stats["prompt_tokens"] += ptok
            self.stats["completion_tokens"] += ctok
            return GenerationResult(
                text=text, model=name, prompt_tokens=ptok, completion_tokens=ctok, finish_reason=reason,
                latency_s=time.monotonic() - started, attempts=attempts, continuations=continuations,
                fallback_used=idx > 0, incomplete=detect_incomplete(text, reason, expect_json),
                uncertain=detect_uncertainty(text))
        raise ModelUnavailable("Ningún modelo pudo responder", errors)

    async def stream(self, messages: list[dict], model: str) -> AsyncIterator[str]:
        """Streaming sin reintentos a mitad de flujo: solo se reintenta antes del primer fragmento."""
        cfg = self.get(model)
        self.stats["requests"] += 1
        for attempt in range(1, self.max_retries + 2):
            started_yielding = False
            try:
                async for piece in self.transport.chat_stream(cfg.name, messages, cfg.options(), cfg.keep_alive):
                    started_yielding = True
                    yield piece
                return
            except TransportError as exc:
                if started_yielding or not exc.retryable or attempt > self.max_retries:
                    self.stats["failures"] += 1
                    raise
                self.stats["retries"] += 1
                await self._sleep(self.backoff_s * (2 ** (attempt - 1)))
