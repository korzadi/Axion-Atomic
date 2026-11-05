import unittest
from core.errors import ModelConfigError, ModelUnavailable, TransportError
from core.models import ModelConfig, ModelManager, detect_incomplete
from tests.fakes import ScriptedTransport, no_sleep, ok

A, B = ModelConfig("a"), ModelConfig("b")
MSG = [{"role": "user", "content": "hola"}]


def mgr(script, **kw):
    m = ModelManager(ScriptedTransport(script), sleep=no_sleep, **kw)
    m.register(A); m.register(B)
    return m


class ModelManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_then_success(self):
        m = mgr([TransportError("x"), TransportError("y"), ok("hecho")])
        r = await m.generate(MSG, "a")
        self.assertEqual((r.text, r.attempts, m.stats["retries"]), ("hecho", 3, 2))

    async def test_non_retryable_not_retried(self):
        m = mgr([TransportError("404", retryable=False)])
        with self.assertRaises(ModelUnavailable):
            await m.generate(MSG, "a")
        self.assertEqual(len(m.transport.calls), 1)

    async def test_fallback(self):
        m = mgr([TransportError("a1", False), ok("desde b")])
        r = await m.generate(MSG, "a", ["b"])
        self.assertEqual((r.model, r.fallback_used, m.stats["fallbacks"]), ("b", True, 1))

    async def test_all_fail_reports_errors(self):
        m = mgr([TransportError("a1", False), TransportError("b1", False)])
        with self.assertRaises(ModelUnavailable) as cm:
            await m.generate(MSG, "a", ["b"])
        self.assertEqual(len(cm.exception.errors), 2)

    async def test_length_continuation_sums_tokens(self):
        m = mgr([ok("parte1 ", "length", 10, 5), ok("parte2", "stop", 20, 7)])
        r = await m.generate(MSG, "a")
        self.assertEqual((r.text, r.continuations, r.prompt_tokens, r.completion_tokens, r.incomplete),
                         ("parte1 parte2", 1, 30, 12, None))

    async def test_unclosed_fence_continues(self):
        m = mgr([ok("```py\nx=1"), ok("\n```")])
        r = await m.generate(MSG, "a")
        self.assertIsNone(r.incomplete)
        self.assertEqual(r.continuations, 1)

    async def test_continuations_are_bounded(self):
        m = mgr([ok("a", "length")] * 3, max_continuations=2)
        r = await m.generate(MSG, "a")
        self.assertEqual((r.continuations, r.incomplete), (2, "length"))

    async def test_invalid_json_flagged(self):
        r = await mgr([ok("no es json")]).generate(MSG, "a", expect_json=True)
        self.assertEqual(r.incomplete, "invalid_json")

    async def test_uncertainty_flag(self):
        r = await mgr([ok("No estoy seguro de que esto compile")]).generate(MSG, "a")
        self.assertTrue(r.uncertain)

    async def test_stream_retries_only_before_first_chunk(self):
        m = mgr([[TransportError("x")], ["ho", "la"]])
        self.assertEqual([p async for p in m.stream(MSG, "a")], ["ho", "la"])
        m2 = mgr([["ho", TransportError("corte")]])
        got = []
        with self.assertRaises(TransportError):
            async for p in m2.stream(MSG, "a"):
                got.append(p)
        self.assertEqual(got, ["ho"])

    def test_memory_budget_and_params(self):
        m = ModelManager(ScriptedTransport([]), memory_budget_gb=9)
        with self.assertRaises(ModelConfigError):
            m.register(ModelConfig("grande", est_memory_gb=20))
        with self.assertRaises(ModelConfigError):
            m.register(ModelConfig("mal", num_ctx=1024, max_output_tokens=2048))
        with self.assertRaises(ModelConfigError):
            m.get("no-existe")

    def test_detect_incomplete_empty(self):
        self.assertEqual(detect_incomplete("  ", "stop"), "empty")


if __name__ == "__main__":
    unittest.main()
