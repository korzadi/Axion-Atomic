import unittest
from rag.chunker import MAX_CHARS, chunk_file
from rag.lexical import bm25_rank, query_terms, tokenize

PY = '''import os

X = 1


@decorator
def alpha(a):
    """doc"""
    return a + 1


class Beta:
    def m1(self):
        return 1

    def m2(self):
        return 2
'''


def check_ranges(test, text, chunks):
    lines = text.splitlines()
    for c in chunks:
        test.assertEqual(c.text, "\n".join(lines[c.start_line - 1:c.end_line]))


class ChunkerTests(unittest.TestCase):
    def test_python_symbols_and_decorators(self):
        chunks = chunk_file("m.py", PY, max_chars=80)
        check_ranges(self, PY, chunks)
        syms = [c.symbol for c in chunks]
        joined = " | ".join(s or "" for s in syms)
        for name in ("alpha", "Beta.m1", "Beta.m2"):
            self.assertIn(name, joined)
        alpha = next(c for c in chunks if c.symbol and "alpha" in c.symbol)
        self.assertIn("@decorator", alpha.text)

    def test_small_file_merges_into_one_chunk(self):
        chunks = chunk_file("m.py", PY)
        self.assertEqual(len(chunks), 1); check_ranges(self, PY, chunks)
        self.assertIn("alpha", chunks[0].symbol)

    def test_large_class_splits_into_methods(self):
        body = "\n".join(f"    def method_{i}(self):\n        return {'x' * 150!r}\n" for i in range(20))
        src = "class Big:\n    '''doc'''\n\n" + body
        chunks = chunk_file("b.py", src)
        check_ranges(self, src, chunks)
        self.assertTrue(all(len(c.text) <= MAX_CHARS + 200 for c in chunks))
        self.assertGreater(len(chunks), 3)
        self.assertTrue(any("Big.method_0" in (c.symbol or "") for c in chunks))
        self.assertTrue(any("def method_19" in c.text for c in chunks))     # nada se pierde al dividir

    def test_syntax_error_falls_back_to_windows(self):
        src = "def (:\n" + "linea\n" * 600
        chunks = chunk_file("x.py", src); check_ranges(self, src, chunks)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].start_line, 1); self.assertEqual(chunks[-1].end_line, 601)

    def test_windows_overlap_and_progress(self):
        src = "\n".join(f"l{i}" + "z" * 100 for i in range(100))
        chunks = chunk_file("t.txt", src, max_chars=500, overlap=2)
        for a, b in zip(chunks, chunks[1:]):
            self.assertLess(b.start_line, a.end_line + 1)             # solape
            self.assertGreater(b.start_line, a.start_line)           # progreso
        self.assertEqual(chunks[-1].end_line, 100)

    def test_markdown_headings(self):
        md = "intro " + "a" * 30 + "\n\n# Título\n" + "b" * 40 + "\n\n## Sección B\n" + "c" * 40 + "\n"
        chunks = chunk_file("README.md", md, max_chars=60)
        check_ranges(self, md, chunks)
        self.assertEqual([c.symbol for c in chunks], [None, "Título", "Sección B"])

    def test_js_declarations(self):
        js = "const a = 1;\nexport function foo() {\n  return 1;\n}\n\nclass Bar {\n  x() {}\n}\n"
        chunks = chunk_file("a.js", js, max_chars=40)
        syms = [c.symbol for c in chunks]
        self.assertIn("foo", syms); self.assertIn("Bar", syms); check_ranges(self, js, chunks)

    def test_empty_and_giant_line(self):
        self.assertEqual(chunk_file("a.py", "  \n"), [])
        c = chunk_file("a.js", "x" * 50000)
        self.assertEqual(len(c), 1); self.assertLessEqual(len(c[0].text), 6000)


class LexicalTests(unittest.TestCase):
    def test_tokenize_splits_identifiers(self):
        t = tokenize("calcularImpuesto snake_case_name HTTPServer")
        for w in ("calcularimpuesto", "calcular", "impuesto", "snake", "case", "name"):
            self.assertIn(w, t)

    def test_bm25_prefers_relevant(self):
        docs = [("a", "def tax_rate(): return 0.21"), ("b", "def render_page(): return html"), ("c", "tax tax tax invoice")]
        ranked = bm25_rank(query_terms("tax rate"), docs)
        self.assertEqual(ranked[0][0], "a"); self.assertNotIn("b", [i for i, _ in ranked])

    def test_empty_inputs(self):
        self.assertEqual(bm25_rank([], [("a", "x")]), []); self.assertEqual(bm25_rank(["x"], []), [])


if __name__ == "__main__":
    unittest.main()
