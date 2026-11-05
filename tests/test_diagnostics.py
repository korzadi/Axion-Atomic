import unittest
from agent.diagnostics import normalize_path, parse_diagnostics, parse_test_output, render_diagnostics

PY_TB = '''Traceback (most recent call last):
  File "/workspace/app.py", line 10, in <module>
    main()
  File "/workspace/app.py", line 6, in main
    helper(1)
  File "/usr/local/lib/python3.12/site-packages/lib/x.py", line 99, in helper
    raise KeyError("k")
KeyError: 'k'
'''
SYNTAX = '''  File "/workspace/bad.py", line 3
    def (:
        ^
SyntaxError: invalid syntax
'''
RUST = '''error[E0425]: cannot find value `x` in this scope
 --> src/main.rs:2:13
  |
2 |     let y = x;
error: aborting due to 1 previous error
'''


class DiagnosticsTests(unittest.TestCase):
    def test_python_traceback_picks_project_frame(self):
        (d,) = parse_diagnostics(PY_TB)
        self.assertEqual((d.file, d.line, d.code, d.message), ("app.py", 6, "KeyError", "'k'"))

    def test_python_syntax_error(self):
        (d,) = parse_diagnostics(SYNTAX)
        self.assertEqual((d.kind, d.file, d.line, d.code), ("python_syntax", "bad.py", 3, "SyntaxError"))

    def test_gcc_clang(self):
        out = "In file included from a.h:1:\nmain.c:3:5: error: expected ';' before 'return'\nmain.c:7:1: warning: unused variable 'x'\nmain.c:9: fatal error: nope.h: No such file\n"
        ds = parse_diagnostics(out)
        self.assertEqual([(d.line, d.severity) for d in ds], [(3, "error"), (7, "warning"), (9, "error")])
        self.assertEqual(ds[0].col, 5); self.assertIsNone(ds[2].col)

    def test_tsc_go_javac_rustc(self):
        out = ("src/a.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.\n./main.go:8:2: undefined: foo\n"
               "Main.java:5: error: ';' expected\n" + RUST)
        ds = {d.kind: d for d in parse_diagnostics(out)}
        self.assertEqual((ds["tsc"].file, ds["tsc"].code, ds["tsc"].col), ("src/a.ts", "TS2322", 5))
        self.assertEqual((ds["go"].file, ds["go"].line), ("main.go", 8)); self.assertEqual(ds["javac"].line, 5)
        self.assertEqual((ds["rustc"].file, ds["rustc"].code, ds["rustc"].line), ("src/main.rs", "E0425", 2))
        self.assertEqual(len(parse_diagnostics(RUST)), 1)                         # "aborting" no cuenta

    def test_dedup_limit_and_clean_output(self):
        self.assertEqual(len(parse_diagnostics("a.c:1:1: error: x\n" * 5)), 1)
        many = "".join(f"a.c:{i}:1: error: e{i}\n" for i in range(100))
        self.assertEqual(len(parse_diagnostics(many, limit=10)), 10)
        self.assertEqual(parse_diagnostics("todo bien\nOK\n"), [])
        self.assertIn("app.py:6", render_diagnostics(parse_diagnostics(PY_TB)))

    def test_normalize_path(self):
        self.assertEqual(normalize_path("/workspace/a/b.py"), "a/b.py"); self.assertEqual(normalize_path("./x.go"), "x.go")


class TestOutputParsers(unittest.TestCase):
    def test_unittest(self):
        s = parse_test_output("unittest", "..F\n" + "=" * 70 + "\nFAIL: test_b (test_sample.T.test_b)\n" + "-" * 70 + "\nRan 3 tests in 0.001s\n\nFAILED (failures=1)\n")
        self.assertEqual((s.passed, s.failed, s.errors, s.ok, s.failures), (2, 1, 0, False, ["test_sample.T.test_b"]))
        s = parse_test_output("unittest", "...\n" + "-" * 70 + "\nRan 3 tests in 0.0s\n\nOK (skipped=1)\n")
        self.assertEqual((s.passed, s.skipped, s.ok), (2, 1, True))
        self.assertFalse(parse_test_output("unittest", "ImportError: no module").ok)       # sin pruebas ejecutadas no es "ok"

    def test_pytest(self):
        s = parse_test_output("pytest", "FAILED test_a.py::test_x - assert 1 == 2\nERROR test_b.py::test_y\n=========== 1 failed, 2 passed, 1 error in 0.05s ===========\n")
        self.assertEqual((s.passed, s.failed, s.errors, s.failures), (2, 1, 1, ["test_a.py::test_x", "test_b.py::test_y"]))
        self.assertTrue(parse_test_output("pytest", "...\n3 passed in 0.01s\n").ok)

    def test_go_cargo_and_unknown(self):
        g = parse_test_output("go", "--- FAIL: TestA (0.00s)\nFAIL\nok  \tpkg/b\t0.01s\n")
        self.assertEqual((g.failed, g.failures, g.passed), (1, ["TestA"], 1))
        c = parse_test_output("cargo", "test a ... ok\ntest b ... FAILED\ntest result: FAILED. 1 passed; 1 failed; 0 ignored; 0 measured\n")
        self.assertEqual((c.passed, c.failed, c.failures), (1, 1, ["b"]))
        with self.assertRaises(ValueError): parse_test_output("rspec", "x")


if __name__ == "__main__":
    unittest.main()
