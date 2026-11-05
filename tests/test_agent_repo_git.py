import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.approval_gate import InMemoryApprovalGate
from agent.git import GitError, GitManager
from agent.repo import analyze, render
from agent.workspace import AccessDenied, ConflictError, Workspace

FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


def sh(root, *a):
    subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True,
                   env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})


class RepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        r = self.root = Path(self.tmp.name)
        (r / "pkg").mkdir(); (r / "web").mkdir(); (r / "node_modules").mkdir()
        (r / "pkg/__init__.py").write_text("")
        (r / "pkg/core.py").write_text("from pkg import util\nimport os\n")
        (r / "pkg/util.py").write_text("X = 1\n")
        (r / "pkg/broken.py").write_text("def (:\n")
        (r / "main.py").write_text("from pkg.core import run\nfrom pkg import util\n")
        (r / "web/index.js").write_text("import a from './a'\nconst b = require('../pkg/x.js')\nimport r from 'react'\n")
        (r / "web/a.ts").write_text("export const a = 1\n")
        (r / "package.json").write_text(json.dumps({"dependencies": {"react": "1"}, "devDependencies": {"jest": "1"}}))
        (r / "requirements.txt").write_text("fastapi==0.1\n# c\nhttpx>=0.2\n")
        (r / "leak.py").write_text(f'K = "{FAKE_AWS}"\n')
        (r / ".env").write_text("A=1")
        (r / "node_modules/x.js").write_text("x")
        self.s = analyze(Workspace(r, "p"))

    def test_languages_and_manifests(self):
        self.assertIn("Python", self.s["languages"]); self.assertIn("JavaScript", self.s["languages"])
        self.assertEqual(sorted(self.s["manifests"]), ["package.json", "requirements.txt"])
        self.assertIn("main.py", self.s["entry_points"])
        self.assertEqual(self.s["dependencies"]["package.json"], ["jest", "react"])
        self.assertEqual(self.s["dependencies"]["requirements.txt"], ["fastapi", "httpx"])

    def test_python_import_graph(self):
        self.assertEqual(self.s["imports"]["main.py"], ["pkg/core.py", "pkg/util.py"])
        self.assertEqual(self.s["imports"]["pkg/core.py"], ["pkg/util.py"])
        self.assertEqual(self.s["python_parse_errors"], ["pkg/broken.py"])

    def test_js_relative_imports_only(self):
        self.assertEqual(self.s["imports"]["web/index.js"], ["web/a.ts"])   # 'react' y el archivo inexistente no cuentan

    def test_exclusions_and_secret_paths(self):
        self.assertNotIn(".env", json.dumps(self.s)); self.assertNotIn("node_modules", json.dumps(self.s["imports"]))
        self.assertEqual(self.s["files_with_possible_secrets"], ["leak.py"])
        self.assertNotIn(FAKE_AWS, json.dumps(self.s)); self.assertNotIn(FAKE_AWS, render(self.s))

    def test_render_truncates(self):
        self.assertLessEqual(len(render(self.s, 200)), 230)


class GitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        r = self.root = Path(self.tmp.name)
        sh(r, "init", "-q", "-b", "main")
        sh(r, "config", "user.name", "T"); sh(r, "config", "user.email", "t@t")
        (r / "a.txt").write_text("uno\n"); (r / ".env").write_text("SECRET=zzzzzzzzzz\n")
        sh(r, "add", "a.txt"); sh(r, "commit", "-qm", "inicial")
        self.ws = Workspace(r, "p"); self.git = GitManager(self.ws); self.gate = InMemoryApprovalGate()

    def approve(self, prop):
        pid = self.gate.request(prop); self.gate.decide(pid, True, "ana")
        return self.gate.redeem(pid, prop.action_hash)

    def test_read_ops(self):
        self.assertTrue(self.git.is_repo())
        (self.root / "a.txt").write_text("uno\ndos\n")
        self.assertIn("+dos", self.git.diff()); self.assertIn("inicial", self.git.log())
        self.assertIn("a.txt", self.git.status())

    def test_diff_excludes_sensitive(self):
        sh(self.root, "add", "-f", ".env"); sh(self.root, "commit", "-qm", "oops")
        (self.root / ".env").write_text("SECRET=cambiado1234\n")
        self.assertNotIn("cambiado1234", self.git.diff())
        with self.assertRaises(AccessDenied): self.git.diff(".env")

    def test_commit_requires_matching_approval_and_only_listed_paths(self):
        (self.root / "a.txt").write_text("uno\ndos\n"); (self.root / "b.txt").write_text("b\n"); (self.root / "otro.txt").write_text("o\n")
        prop = self.git.propose_commit("agrega dos", ["a.txt", "b.txt"], "prueba")
        before = sh and subprocess.run(["git", "-C", str(self.root), "rev-list", "--count", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(before, "1")                                   # proponer no confirma nada
        msg = self.git.apply_commit("agrega dos", ["a.txt", "b.txt"], prop, self.approve(prop))
        self.assertIn("agrega dos", msg)
        tracked = subprocess.run(["git", "-C", str(self.root), "ls-files"], capture_output=True, text=True).stdout.split()
        self.assertIn("b.txt", tracked); self.assertNotIn("otro.txt", tracked)

    def test_commit_stale_and_wrong_approval(self):
        (self.root / "a.txt").write_text("v1\n")
        prop = self.git.propose_commit("m", ["a.txt"], "t"); ap = self.approve(prop)
        (self.root / "a.txt").write_text("v2\n")
        with self.assertRaises(ConflictError): self.git.apply_commit("m", ["a.txt"], prop, ap)
        other = self.git.propose_commit("otro mensaje", ["a.txt"], "t")
        with self.assertRaises(ConflictError): self.git.apply_commit("m", ["a.txt"], other, ap)

    def test_commit_refuses_sensitive_and_bad_input(self):
        with self.assertRaises(AccessDenied): self.git.propose_commit("m", [".env"], "t")
        with self.assertRaises(ValueError): self.git.propose_commit("  ", ["a.txt"], "t")
        with self.assertRaises(ValueError): self.git.propose_commit("m", [], "t")

    def test_hooks_are_disabled(self):
        hook = self.root / ".git/hooks/pre-commit"; hook.write_text("#!/bin/sh\ntouch /tmp/hook_ejecutado_axion\nexit 1\n"); hook.chmod(0o755)
        (self.root / "a.txt").write_text("h\n")
        prop = self.git.propose_commit("m", ["a.txt"], "t")
        self.git.apply_commit("m", ["a.txt"], prop, self.approve(prop))          # no falla: el hook no corre
        self.assertFalse(Path("/tmp/hook_ejecutado_axion").exists())

    def test_branch_validation_and_creation(self):
        for bad in ("-x", "a..b", "x y", "", "a.lock", "--help"):
            with self.assertRaises(ValueError, msg=bad): self.git.propose_create_branch(bad, "t")
        prop = self.git.propose_create_branch("feature/x", "t")
        self.assertEqual(self.git.apply_create_branch("feature/x", prop, self.approve(prop)), "Rama activa: feature/x")
        self.assertIn("feature/x", self.git.status())

    def test_not_a_repo(self):
        with tempfile.TemporaryDirectory() as d:
            g = GitManager(Workspace(d, "p"))
            self.assertFalse(g.is_repo())
            with self.assertRaises(GitError): g.status()


if __name__ == "__main__":
    unittest.main()
