"""Transporte HTTP hacia el Ollama EXISTENTE (API documentada: /api/chat, /api/tags). Solo biblioteca estándar.
Nunca reinstala ni modifica Ollama: únicamente consume su API."""
import asyncio
import json
from typing import AsyncIterator

from core.errors import TransportError
from core.http import open_url
from core.models import ChatResponse


class OllamaTransport:
    def __init__(self, base_url: str, timeout: float = 300.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _open(self, path: str, payload: dict | None):
        return open_url("POST" if payload is not None else "GET", self.base + path, payload, timeout=self.timeout)

    def _post_json(self, path: str, payload: dict | None) -> dict:
        with self._open(path, payload) as resp:
            try:
                return json.loads(resp.read())
            except ValueError as exc:
                raise TransportError("Respuesta de Ollama no es JSON válido", retryable=False) from exc

    async def chat(self, model, messages, options, keep_alive) -> ChatResponse:
        data = await asyncio.to_thread(self._post_json, "/api/chat", {
            "model": model, "messages": messages, "stream": False, "options": options, "keep_alive": keep_alive})
        try:
            return ChatResponse(content=data["message"]["content"], finish_reason=data.get("done_reason", "stop"),
                                prompt_tokens=int(data.get("prompt_eval_count", 0)),
                                completion_tokens=int(data.get("eval_count", 0)))
        except (KeyError, TypeError, ValueError) as exc:
            raise TransportError("Formato inesperado en la respuesta de /api/chat", retryable=False) from exc

    async def chat_stream(self, model, messages, options, keep_alive) -> AsyncIterator[str]:
        resp = await asyncio.to_thread(self._open, "/api/chat", {
            "model": model, "messages": messages, "stream": True, "options": options, "keep_alive": keep_alive})
        try:
            while True:
                line = await asyncio.to_thread(resp.readline)
                if not line:
                    break
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise TransportError("Fragmento de streaming inválido", retryable=False) from exc
                piece = obj.get("message", {}).get("content", "")
                if piece:
                    yield piece
                if obj.get("done"):
                    break
        finally:
            resp.close()

    async def list_models(self) -> set[str]:
        data = await asyncio.to_thread(self._post_json, "/api/tags", None)
        return {m["name"] for m in data.get("models", [])}

    async def embed(self, model: str, inputs: list[str]) -> list[list[float]]:
        """POST /api/embed (lote). Devuelve un vector por entrada, en el mismo orden."""
        data = await asyncio.to_thread(self._post_json, "/api/embed", {"model": model, "input": inputs})
        vecs = data.get("embeddings")
        if not isinstance(vecs, list) or len(vecs) != len(inputs):
            raise TransportError("Respuesta de /api/embed inesperada", retryable=False)
        return vecs
