import os
import tempfile
import unittest
from pathlib import Path

from agent.approval_gate import ApprovalError, InMemoryApprovalGate
from agent.ignore import IgnoreRules
from agent.secrets import find_secrets, is_sensitive_path, redact
from agent.workspace import AccessDenied, ConflictError, PathViolation, Workspace, resolve_within

FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"     # formato válido, valor de ejemplo inexistente
FAKE_GH = "ghp_" + "a" * 36


class SecretsTests(unittest.TestCase):
    def test_sensitive_paths(self):
        for p in (".env", "app/.env.production", "keys/server.pem", ".ssh/config", "id_rsa", "a/credentials.json"):
            self.assertTrue(is_sensitive_path(p), p)
        for p in (".env.example", "src/main.py", "README.md"):
            self.assertFalse(is_sensitive_path(p), p)

    def test_find_and_redact(self):
        text = f'a = 1\nkey = "{FAKE_AWS}"\ntoken: {FAKE_GH}\npassword = "supersecretvalue"\n'
        kinds = {f.kind for f in find_secrets(text)}
        self.assertTrue({"aws_access_key", "github_token", "credential_assignment"} <= kinds)
        red = redact(text)
        self.assertNotIn(FAKE_AWS, red); self.assertNotIn(FAKE_GH, red); self.assertNotIn("supersecretvalue", red)
        self.assertIn("a = 1", red)

    def test_no_false_positive_on_plain_code(self):
        self.assertEqual(find_secrets("password = get_password()\nx = 'hola'"), [])


class IgnoreTests(unittest.TestCase):
    def test_rules(self):
        r = IgnoreRules(["*.log", "build/", "/root_only.txt", "docs/**/tmp", "!keep.log", "# c"])
        self.assertTrue(r.is_ignored("a/b/x.log"))
        self.assertFalse(r.is_ignored("a/keep.log"))
        self.assertTrue(r.is_ignored("build", True)); self.assertTrue(r.is_ignored("build/x.py"))
        self.assertFalse(r.is_ignored("build"))                  # 'build/' solo aplica a directorios
        self.assertTrue(r.is_ignored("root_only.txt")); self.assertFalse(r.is_ignored("sub/root_only.txt"))
        self.assertTrue(r.is_ignored("docs/a/b/tmp", True))


class GateTests(unittest.TestCase):
    def _prop(self, ws, content="x"):
        return ws.propose_write("a.txt", content, "prueba")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace(self.tmp.name, "p1")
        self.t = [0.0]
        self.gate = InMemoryApprovalGate(ttl_s=100, clock=lambda: self.t[0])

    def test_flow_single_use_and_bound(self):
        ch = self._prop(self.ws)
        pid = self.gate.request(ch.proposal)
        with self.assertRaises(ApprovalError): self.gate.redeem(pid, ch.proposal.action_hash)   # aún pendiente
        self.gate.decide(pid, True, "ana")
        with self.assertRaises(ApprovalError): self.gate.redeem(pid, "otro-hash")              # acción distinta
        ap = self.gate.redeem(pid, ch.proposal.action_hash)
        self.assertEqual(self.ws.apply(ch, ap), "Creado a.txt")
        with self.assertRaises(ApprovalError): self.gate.redeem(pid, ch.proposal.action_hash)  # un solo uso

    def test_rejected_expired_and_double_decision(self):
        pid = self.gate.request(self._prop(self.ws).proposal)
        self.gate.decide(pid, False, "ana", "no")
        self.assertEqual(self.gate.status(pid), ("rejected", "no"))
        with self.assertRaises(ApprovalError): self.gate.decide(pid, True, "ana")
        pid2 = self.gate.request(self._prop(self.ws, "y").proposal)
        self.t[0] = 1000
        with self.assertRaises(ApprovalError): self.gate.decide(pid2, True, "ana")
        self.assertEqual(self.gate.status(pid2)[0], "expired")

    def test_reviewer_required(self):
        pid = self.gate.request(self._prop(self.ws).proposal)
        with self.assertRaises(ApprovalError): self.gate.decide(pid, True, "  ")

    def test_approval_for_other_change_cannot_apply(self):
        a, b = self._prop(self.ws, "A"), self._prop(self.ws, "B")
        pid = self.gate.request(a.proposal); self.gate.decide(pid, True, "ana")
        ap = self.gate.redeem(pid, a.proposal.action_hash)
        with self.assertRaises(ConflictError): self.ws.apply(b, ap)
        self.assertFalse((Path(self.tmp.name) / "a.txt").exists())


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("print('hi')\nx = 1\n")
        (self.root / ".env").write_text("TOKEN=abc")
        (self.root / ".gitignore").write_text("ignored/\n*.tmp\n")
        (self.root / "ignored").mkdir(); (self.root / "ignored" / "z.py").write_text("z")
        (self.root / "bin.dat").write_bytes(b"\0\1\2")
        (self.root / "leak.py").write_text(f'KEY = "{FAKE_AWS}"\n')
        self.ws = Workspace(self.root, "p1")
        self.gate = InMemoryApprovalGate()

    def approve(self, ch):
        pid = self.gate.request(ch.proposal); self.gate.decide(pid, True, "ana")
        return self.gate.redeem(pid, ch.proposal.action_hash)

    def test_path_traversal_variants(self):
        for bad in ("../x", "src/../../x", "/etc/passwd", "a\0b"):
            with self.assertRaises(PathViolation, msg=bad): self.ws.read(bad)
        with self.assertRaises(PathViolation): resolve_within(self.root, "../../etc/passwd")

    def test_symlink_escape_blocked(self):
        outside = tempfile.TemporaryDirectory(); self.addCleanup(outside.cleanup)
        (Path(outside.name) / "secret.txt").write_text("fuera")
        os.symlink(outside.name, self.root / "link")
        with self.assertRaises(PathViolation): self.ws.read("link/secret.txt")
        self.assertNotIn("link", [e["name"] for e in self.ws.list_dir(".")])

    def test_denied_sensitive_ignored_binary(self):
        for rel in (".env", "ignored/z.py", "bin.dat"):
            with self.assertRaises(AccessDenied, msg=rel): self.ws.read(rel)

    def test_read_redacts_and_ranges(self):
        self.assertNotIn(FAKE_AWS, self.ws.read("leak.py"))
        self.assertEqual(self.ws.read("src/app.py", start_line=2, end_line=2), "2: x = 1")

    def test_walk_and_search_skip_excluded(self):
        files = set(self.ws.walk())
        self.assertIn("src/app.py", files)
        self.assertFalse({".env", "ignored/z.py", ".git"} & files)
        hits = self.ws.search("print")
        self.assertEqual([(h["path"], h["line"]) for h in hits], [("src/app.py", 1)])
        self.assertEqual(self.ws.search("TOKEN"), [])            # .env no se busca

    def test_edit_requires_unique_match(self):
        with self.assertRaises(ValueError): self.ws.propose_edit("src/app.py", "zzz", "y", "t")
        (self.root / "dup.py").write_text("a\na\n")
        with self.assertRaises(ValueError): self.ws.propose_edit("dup.py", "a", "b", "t")

    def test_write_edit_delete_with_approval(self):
        ch = self.ws.propose_edit("src/app.py", "x = 1", "x = 2", "cambiar x")
        self.assertIn("-x = 1", ch.diff); self.assertIn("+x = 2", ch.diff)
        self.assertIn("x = 1", (self.root / "src/app.py").read_text())   # propuesta no modifica
        self.ws.apply(ch, self.approve(ch))
        self.assertIn("x = 2", (self.root / "src/app.py").read_text())
        d = self.ws.propose_delete("src/app.py", "limpieza")
        self.ws.apply(d, self.approve(d))
        self.assertFalse((self.root / "src/app.py").exists())

    def test_stale_file_conflict(self):
        ch = self.ws.propose_edit("src/app.py", "x = 1", "x = 9", "t")
        ap = self.approve(ch)
        (self.root / "src/app.py").write_text("print('otro')\nx = 1\n")
        with self.assertRaises(ConflictError): self.ws.apply(ch, ap)

    def test_cannot_write_sensitive_or_git(self):
        for rel in (".env", ".git/config", "keys/id_rsa"):
            with self.assertRaises(AccessDenied, msg=rel): self.ws.propose_write(rel, "x", "t")

    def test_secret_in_new_content_flagged(self):
        ch = self.ws.propose_write("n.py", f'K = "{FAKE_AWS}"', "t")
        self.assertTrue(any("secretos" in r for r in ch.proposal.risks))

    def test_apply_preserves_mode_and_leaves_no_temp(self):
        p = self.root / "run.sh"; p.write_text("a"); p.chmod(0o750)
        ch = self.ws.propose_write("run.sh", "b", "t"); self.ws.apply(ch, self.approve(ch))
        self.assertEqual(p.stat().st_mode & 0o777, 0o750)
        self.assertEqual([f for f in os.listdir(self.root) if f.startswith(".axion-")], [])


if __name__ == "__main__":
    unittest.main()
