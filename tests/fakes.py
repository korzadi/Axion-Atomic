"""Transporte guionizado para pruebas unitarias del Model Manager/Engine (no simula Ollama real:
las pruebas de HTTP usan un servidor local en test_ollama_transport.py)."""
from core.errors import TransportError
from core.models import ChatResponse


class ScriptedTransport:
    def __init__(self, script, models=None):
        self.script = list(script)   # ChatResponse | TransportError | list[str|TransportError] (streams)
        self.calls = []
        self.models = models or set()

    async def chat(self, model, messages, options, keep_alive):
        self.calls.append((model, messages))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def chat_stream(self, model, messages, options, keep_alive):
        self.calls.append((model, messages))
        for piece in self.script.pop(0):
            if isinstance(piece, Exception):
                raise piece
            yield piece

    async def list_models(self):
        return self.models


async def no_sleep(_):
    return None


def ok(text, reason="stop", p=10, c=5):
    return ChatResponse(text, reason, p, c)
