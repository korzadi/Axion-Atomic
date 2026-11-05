import unittest
from core.context import ContextManager
from core.errors import ContextOverflow, NoSuitableModel
from core.models import ModelConfig
from core.router import ModelRouter, TaskKind

def hist(n, size=400):
    out = []
    for i in range(n):
        out.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i} " + "x" * size})
    return out


class ContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_fits_without_summary(self):
        f = await ContextManager(4096, 512).fit("sys", hist(2))
        self.assertFalse(f.summarized)
        self.assertEqual(len(f.messages), 3)

    async def test_summarizes_old_and_keeps_recent(self):
        async def summ(prior, older):
            return "RESUMEN:" + str(len(older))
        cm = ContextManager(1200, 200, keep_recent=2, summarizer=summ)
        f = await cm.fit("sys", hist(12))
        self.assertTrue(f.summarized)
        self.assertTrue(f.summary.startswith("RESUMEN:"))
        self.assertEqual(f.recent[-1]["content"][:3], "m11")
        self.assertLessEqual(f.estimated_tokens, 1000)

    async def test_summarizer_failure_uses_digest(self):
        async def boom(prior, older):
            raise RuntimeError("modelo caído")
        f = await ContextManager(1200, 200, 2, summarizer=boom).fit("sys", hist(12))
        self.assertTrue(f.summarizer_failed)
        self.assertIn("- user:", f.summary)

    async def test_last_message_too_big_raises(self):
        with self.assertRaises(ContextOverflow):
            await ContextManager(1000, 200).fit("sys", [{"role": "user", "content": "y" * 20000}])

    async def test_extra_context_truncated(self):
        f = await ContextManager(2000, 500).fit("sys", hist(1), extra_context="z" * 50000)
        self.assertTrue(f.extra_truncated)
        self.assertLessEqual(f.estimated_tokens, 1500)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.big = ModelConfig("big", num_ctx=8192)
        self.small = ModelConfig("small", num_ctx=2048, max_output_tokens=256)
        self.r = ModelRouter([self.big, self.small], {"*": ["big", "small"], "summary": ["small"]})

    def test_default_and_specific_route(self):
        self.assertEqual(self.r.select(TaskKind.CHAT, 100).model, "big")
        self.assertEqual(self.r.select(TaskKind.SUMMARY, 100).model, "small")

    def test_skips_unavailable_and_too_small(self):
        d = self.r.select(TaskKind.CHAT, 100, available={"small"})
        self.assertEqual(d.model, "small")
        self.assertEqual(self.r.select(TaskKind.CHAT, 3000).fallbacks, [])

    def test_decomposition_flag(self):
        d = self.r.select(TaskKind.CHAT, 6000)
        self.assertTrue(d.needs_decomposition)

    def test_no_model(self):
        with self.assertRaises(NoSuitableModel):
            self.r.select(TaskKind.CHAT, 100, available=set())

    def test_requires_default_route(self):
        with self.assertRaises(NoSuitableModel):
            ModelRouter([self.big], {"chat": ["big"]})


if __name__ == "__main__":
    unittest.main()
