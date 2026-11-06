import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from agent.approval_gate import InMemoryApprovalGate
from agent.workspace import Workspace
from sandbox.backends import LocalBackend, ResourceLimits
from sandbox.executor import NoTestsDetected, SandboxExecutor, detect_test_command, render_result
from sandbox.policy import CommandBlocked, NeedsApproval
from sandbox.snapshot import Snapshot, SnapshotTooLarge

FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
TESTS_PY = '''import unittest
class T(unittest.TestCase):
    def test_a(self): self.assertEqual(1 + 1, 2)
    def test_b(self): self.assertEqual(1 + 1, 3)
    def test_c(self): self.assertTrue(True)
if __name__ == "__main__": unittest.main()
'''


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"AXION_ALLOW_UNSAFE_LOCAL_SANDBOX": "1", "AXION_ALLOW_UNSAFE_LOCAL_NETWORK": "1"}); p.start(); self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.sbx_base = tempfile.TemporaryDirectory(); self.addCleanup(self.sbx_base.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "test_sample.py").write_text(TESTS_PY)
        (self.root / "script.py").write_text("def f():\n    raise ValueError('boom')\nf()\n")
        (self.root / ".env").write_text(f"SECRET={FAKE_AWS}")
        (self.root / "main.c").write_text("int main(void) {\n    int x = 1\n    return x;\n}\n")
        self.ws = Workspace(self.root, "p1"); self.events = []
        self.make()

    def make(self, **limits):
        self.ex = SandboxExecutor(LocalBackend(), self.ws, ResourceLimits(**limits), audit=self.events.append, snapshot_dir=self.sbx_base.name)

    def leftover(self): return os.listdir(self.sbx_base.name)


class SnapshotTests(Base):
    def test_excludes_sensitive_and_cleans_up(self):
        (self.root / "node_modules").mkdir(); (self.root / "node_modules/x.js").write_text("x")
        os.symlink("/etc/passwd", self.root / "link")
        with Snapshot(Workspace(self.root, "p1"), base_dir=self.sbx_base.name) as snap:
            names = {str(p.relative_to(snap)) for p in snap.rglob("*") if p.is_file()}
            self.assertIn("script.py", names)
            self.assertFalse({".env", "node_modules/x.js", "link"} & names)
        self.assertEqual(self.leftover(), [])

    def test_size_limit_and_cleanup_on_error(self):
        with self.assertRaises(SnapshotTooLarge):
            with Snapshot(self.ws, max_bytes=10, base_dir=self.sbx_base.name): pass
        self.assertEqual(self.leftover(), [])


class ExecTests(Base):
    async def test_runs_and_never_modifies_project_or_leaves_files(self):
        before = sorted(os.listdir(self.root))
        res = await self.ex.run_auto("python -c \"open('nuevo.txt','w').write('x'); print('ok')\"")
        self.assertEqual((res.exit_code, res.stdout.strip()), (0, "ok"))
        self.assertEqual(sorted(os.listdir(self.root)), before)
        self.assertEqual(self.leftover(), [])

    async def test_secrets_file_is_not_in_sandbox(self):
        res = await self.ex.run_auto("ls -a")
        self.assertNotIn(".env", res.stdout)
        res = await self.ex.run_auto("cat .env")
        self.assertNotEqual(res.exit_code, 0); self.assertNotIn(FAKE_AWS, res.stdout + res.stderr)

    async def test_timeout_kills_and_reports(self):
        self.make(timeout_s=1)
        t0 = time.monotonic(); res = await self.ex.run_auto("python -c 'import time; time.sleep(20)'")
        self.assertTrue(res.timed_out); self.assertIsNone(res.exit_code); self.assertLess(time.monotonic() - t0, 6)
        self.assertIn("TIEMPO AGOTADO", render_result(res))

    async def test_background_children_do_not_hang_or_survive(self):
        (self.root / "bg.py").write_text("import subprocess\nsubprocess.Popen(['sleep','30'])\nprint('listo')\n")
        t0 = time.monotonic(); res = await self.ex.run_auto("python bg.py")
        self.assertEqual(res.stdout.strip(), "listo"); self.assertLess(time.monotonic() - t0, 6)
        time.sleep(0.3)
        ps = os.popen("ps -eo args | grep '[s]leep 30'").read()
        self.assertEqual(ps, "")

    async def test_output_is_capped_without_blocking(self):
        self.make(max_output_bytes=10_000)
        res = await self.ex.run_auto("python -c \"print('x' * 3000000)\"")
        self.assertTrue(res.truncated); self.assertEqual(len(res.stdout), 10_000)

    async def test_memory_limit_enforced(self):
        self.make(memory_mb=256)
        res = await self.ex.run_auto("python -c \"b = bytearray(2 * 1024**3)\"")
        self.assertNotEqual(res.exit_code, 0); self.assertIn("MemoryError", res.stderr)

    async def test_policy_gates(self):
        with self.assertRaises(CommandBlocked): await self.ex.run_auto("sudo ls")
        with self.assertRaises(CommandBlocked): await self.ex.run_auto("cat /etc/passwd")
        with self.assertRaises(NeedsApproval) as cm: await self.ex.run_auto("pip install requests")
        self.assertTrue(cm.exception.decision.network)
        self.assertEqual(self.events, [])                                         # nada se ejecutó

    async def test_audit_event_for_each_run(self):
        await self.ex.run_auto("python script.py")
        (e,) = self.events
        self.assertEqual((e["type"], e["command"], e["exit_code"], e["backend"]), ("sandbox_run", "python script.py", 1, "local"))

    async def test_traceback_and_compiler_diagnostics_in_output(self):
        out = render_result(await self.ex.run_auto("python script.py"))
        self.assertIn("diagnósticos", out); self.assertIn("script.py:2", out); self.assertIn("ValueError", out)
        self.assertNotIn(self.sbx_base.name, out)                                  # no se filtran rutas temporales
        out = render_result(await self.ex.run_auto("gcc -o a main.c"))
        self.assertIn("main.c:3", out); self.assertIn("error", out)

    async def test_propose_apply_is_bound_to_exact_command(self):
        gate = InMemoryApprovalGate()
        prop, decision = self.ex.propose("bash -c 'echo hola'", "probar")
        self.assertEqual(decision.level, "approval"); self.assertIn("copia temporal", " ".join(prop.risks))
        pid = gate.request(prop); gate.decide(pid, True, "ana")
        res = await self.ex.apply(decision, gate.redeem(pid, prop.action_hash))
        self.assertEqual(res.stdout.strip(), "hola"); self.assertEqual(self.events[-1]["approval_id"], pid)
        other, _ = self.ex.propose("bash -c 'echo otro'", "x")
        self.assertNotEqual(other.action_hash, prop.action_hash)
        with self.assertRaises(CommandBlocked): self.ex.propose("sudo ls", "x")


class TestRunnerTests(Base):
    def test_detection(self):
        self.assertEqual(detect_test_command(self.ws)[0], "unittest")
        (self.root / "go.mod").write_text("module x\n"); self.assertEqual(detect_test_command(self.ws)[0], "go")
        (self.root / "pytest.ini").write_text("[pytest]\n"); self.assertEqual(detect_test_command(self.ws)[0], "pytest")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(NoTestsDetected): detect_test_command(Workspace(d, "p"))

    async def test_run_tests_parses_real_unittest_output(self):
        res, summary = await self.ex.run_tests()
        self.assertEqual(res.exit_code, 1)
        self.assertEqual((summary.passed, summary.failed, summary.errors, summary.ok), (2, 1, 0, False))
        self.assertEqual(summary.failures, ["test_sample.T.test_b"])
        (self.root / "test_sample.py").write_text(TESTS_PY.replace("3)", "2)"))
        res, summary = await self.ex.run_tests()
        self.assertEqual((res.exit_code, summary.passed, summary.ok), (0, 3, True))


if __name__ == "__main__":
    unittest.main()
