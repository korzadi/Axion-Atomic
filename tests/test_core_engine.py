import unittest
from core.engine import Conversation, CoreEngine
from core.errors import ModelUnavailable, TransportError
from core.models import ModelConfig, ModelManager
from core.router import ModelRouter, TaskKind
from tests.fakes import ScriptedTransport, no_sleep, ok


def engine(script, ctx=8192, **kw):
    cfg = ModelConfig("m", num_ctx=ctx, max_output_tokens=256)
    mgr = ModelManager(ScriptedTransport(script), sleep=no_sleep)
    mgr.register(cfg)
    return CoreEngine(mgr, ModelRouter([cfg], {"*": ["m"]}), "Eres un ingeniero.", ctx, 256, **kw)


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_respond_commits_history(self):
        e, c = engine([ok("hola")]), Conversation("p1")
        res, warns = await e.respond(c, "hey")
        self.assertEqual([m["role"] for m in c.history], ["user", "assistant"])
        self.assertEqual((res.text, warns), ("hola", []))
        sent = e.manager.transport.calls[0][1]
        self.assertEqual(sent[0]["role"], "system")

    async def test_failure_leaves_conversation_intact(self):
        e, c = engine([TransportError("x", False)]), Conversation("p1")
        with self.assertRaises(ModelUnavailable):
            await e.respond(c, "hey")
        self.assertEqual(c.history, [])

    async def test_warnings_for_uncertain_and_incomplete(self):
        e, c = engine([ok("No estoy seguro", "length")] * 3), Conversation("p1")
        _, warns = await e.respond(c, "hey")
        self.assertTrue(any("incertidumbre" in w for w in warns))
        self.assertTrue(any("incompleta" in w for w in warns))

    async def test_long_conversation_gets_summarized(self):
        script = [ok("r" * 300)] * 6 + [ok("RESUMEN BREVE")] * 20
        e, c = engine(script, ctx=1200, keep_recent=2), Conversation("p1")
        for i in range(6):
            await e.respond(c, f"pregunta {i} " + "q" * 300)
        self.assertTrue(c.summary)
        self.assertLessEqual(len(c.history), 4)

    async def test_stream_commits(self):
        e, c = engine([["a", "b", "c"]]), Conversation("p1")
        self.assertEqual("".join([p async for p in e.respond_stream(c, "hey")]), "abc")
        self.assertEqual(c.history[-1], {"role": "assistant", "content": "abc"})

    async def test_health_aggregates_and_survives_errors(self):
        async def good(): return True
        async def bad(): raise RuntimeError("x")
        e = engine([], health_checks={"ollama": good, "qdrant": bad})
        self.assertEqual(await e.health(), {"ollama": True, "qdrant": False})


if __name__ == "__main__":
    unittest.main()
