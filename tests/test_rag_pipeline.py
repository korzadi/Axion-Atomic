import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.workspace import Workspace
from core.errors import TransportError
from rag.chunker import Chunk
from rag.indexer import RepoIndexer
from rag.memory import MemoryManager
from rag.retriever import Retriever, format_context
from rag.store import InMemoryVectorStore
from tests.rag_helpers import FailingEmbedder, HashEmbedder, make_meta

FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
TAX = "def calculate_tax(amount, rate):\n    \"\"\"Calcula el impuesto sobre una cantidad.\"\"\"\n    return amount * rate\n"
PAGE = "def render_invoice_page(order):\n    return '<html>' + str(order) + '</html>'\n"


def make_repo(root: Path):
    (root / "src").mkdir(); (root / "node_modules").mkdir()
    (root / "src/tax.py").write_text(TAX); (root / "src/page.py").write_text(PAGE)
    (root / "README.md").write_text("# Demo\nSistema de facturación.\n")
    (root / ".env").write_text("TOKEN=zzzz")
    (root / "node_modules/dep.js").write_text("function dep() {}")
    (root / ".gitignore").write_text("secret_dir/\n")
    (root / "secret_dir").mkdir(); (root / "secret_dir/a.py").write_text("x = 1\n")
    (root / "logo.png").write_bytes(b"\x89PNG\0\0")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})


class PipelineBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); make_repo(self.root)
        self.meta, self.store, self.emb = make_meta(), InMemoryVectorStore(), HashEmbedder()
        self.ws = Workspace(self.root, "p1")
        self.idx = RepoIndexer(self.emb, self.store, self.meta)
        self.ret = Retriever(self.emb, self.store, self.meta)

    def indexed_paths(self, pid="p1"): return set(self.meta.list_files(pid))
    def vec_paths(self, pid="p1"): return {p.payload["path"] for p in self.store.points.values() if p.payload["project_id"] == pid}


class IndexerTests(PipelineBase):
    async def test_initial_index_respects_exclusions(self):
        rep = await self.idx.index_project(self.ws)
        self.assertEqual(self.indexed_paths(), {"src/tax.py", "src/page.py", "README.md", ".gitignore"})
        self.assertEqual(self.vec_paths(), self.indexed_paths())
        for forbidden in (".env", "node_modules/dep.js", "secret_dir/a.py", "logo.png"):
            self.assertNotIn(forbidden, self.indexed_paths())
        self.assertEqual(rep.errors, [])
        self.assertEqual(self.meta.stats("p1")["chunks"], len(self.store.points))

    async def test_incremental_unchanged_modified_removed(self):
        await self.idx.index_project(self.ws)
        calls = self.emb.calls
        rep = await self.idx.index_project(self.ws)
        self.assertEqual((rep.indexed, rep.removed, self.emb.calls), ([], [], calls))      # nada que hacer: 0 embeddings
        (self.root / "src/tax.py").write_text(TAX + "\ndef extra():\n    return 1\n")
        (self.root / "src/page.py").unlink()
        rep = await self.idx.index_project(self.ws)
        self.assertEqual(rep.indexed, ["src/tax.py"]); self.assertEqual(rep.removed, ["src/page.py"])
        self.assertNotIn("src/page.py", self.vec_paths()); self.assertNotIn("src/page.py", self.indexed_paths())
        self.assertEqual(self.meta.stats("p1")["chunks"], len(self.store.points))          # sin huérfanos en ninguno de los dos

    async def test_secrets_never_indexed_and_removed_if_introduced(self):
        (self.root / "src/leak.py").write_text(f'KEY = "{FAKE_AWS}"\n')
        rep = await self.idx.index_project(self.ws)
        self.assertEqual(rep.skipped_secrets, ["src/leak.py"]); self.assertNotIn("src/leak.py", self.indexed_paths())
        self.assertNotIn(FAKE_AWS, " ".join(c["text"] for c in self.meta.lexical_candidates("p1", ["key"])))
        (self.root / "src/tax.py").write_text(TAX + f'\nTOKEN = "{FAKE_AWS}"\n')
        rep = await self.idx.index_project(self.ws)
        self.assertEqual(rep.removed, ["src/tax.py"])                                         # ahora contiene un secreto: se retira
        self.assertNotIn("src/tax.py", self.vec_paths())

    async def test_embedding_failure_keeps_previous_index(self):
        await self.idx.index_project(self.ws)
        before = (set(self.store.points), self.meta.stats("p1"))
        (self.root / "src/tax.py").write_text(TAX + "\n# cambio\n")
        bad = RepoIndexer(FailingEmbedder(), self.store, self.meta)
        rep = await bad.index_project(self.ws)
        self.assertEqual(len(rep.errors), 1); self.assertEqual(rep.removed, [])
        self.assertEqual((set(self.store.points), self.meta.stats("p1")), before)

    async def test_vector_upsert_failure_keeps_previous_file_index(self):
        await self.idx.index_project(self.ws)
        old_ids = set(self.store.points)
        old_sha = self.meta.list_files("p1")["src/tax.py"]
        (self.root / "src/tax.py").write_text(TAX + "\n# cambio de versión\n")

        class FailingStore(InMemoryVectorStore):
            async def upsert(self, points):
                raise TransportError("vector store unavailable", retryable=True)

        failing_store = FailingStore()
        failing_store.points = self.store.points
        bad = RepoIndexer(self.emb, failing_store, self.meta)
        report = await bad.index_project(self.ws)

        self.assertTrue(any("src/tax.py" in error for error in report.errors))
        self.assertEqual(self.meta.list_files("p1")["src/tax.py"], old_sha)
        self.assertEqual(set(failing_store.points), old_ids)
        self.assertIn("src/tax.py", {point.payload["path"] for point in failing_store.points.values()})

    async def test_cleanup_failure_keeps_new_metadata_and_retriever_ignores_old_vectors(self):
        await self.idx.index_project(self.ws)
        old_tax_ids = {
            point.id for point in self.store.points.values()
            if point.payload["project_id"] == "p1" and point.payload["path"] == "src/tax.py"
        }
        old_sha = self.meta.list_files("p1")["src/tax.py"]
        (self.root / "src/tax.py").write_text(TAX + "\n# versión nueva\n")

        class FailingCleanupStore(InMemoryVectorStore):
            async def delete_ids(self, ids):
                raise TransportError("vector cleanup unavailable", retryable=True)

        failing_store = FailingCleanupStore()
        failing_store.points = self.store.points
        indexer = RepoIndexer(self.emb, failing_store, self.meta)
        report = await indexer.index_project(self.ws)

        new_sha = self.meta.list_files("p1")["src/tax.py"]
        self.assertNotEqual(new_sha, old_sha)
        self.assertTrue(any("src/tax.py" in error for error in report.errors))
        self.assertTrue(old_tax_ids.issubset(failing_store.points))
        self.assertTrue(any(
            point.payload["path"] == "src/tax.py" and point.id not in old_tax_ids
            for point in failing_store.points.values()
        ))

        result = await Retriever(self.emb, failing_store, self.meta).retrieve("p1", "calculate_tax rate", limit=10)
        self.assertTrue(any("obsoletas" in warning for warning in result.warnings))
        self.assertTrue(all(chunk.id not in old_tax_ids for chunk in result.chunks))

    async def test_truncated_walk_deletes_nothing(self):
        await self.idx.index_project(self.ws)
        small = RepoIndexer(self.emb, self.store, self.meta, max_files=1)
        rep = await small.index_project(self.ws)
        self.assertTrue(rep.truncated); self.assertEqual(rep.removed, [])
        self.assertEqual(self.indexed_paths(), {"src/tax.py", "src/page.py", "README.md", ".gitignore"})

    async def test_projects_with_same_paths_do_not_mix(self):
        other = tempfile.TemporaryDirectory(); self.addCleanup(other.cleanup)
        (Path(other.name) / "src").mkdir(); (Path(other.name) / "src/tax.py").write_text("def other_project_function():\n    return 'otro'\n")
        await self.idx.index_project(self.ws); await self.idx.index_project(Workspace(other.name, "p2"))
        self.assertEqual(len(self.meta.lexical_candidates("p2", ["other_project_function"])), 1)
        self.assertEqual(self.meta.lexical_candidates("p1", ["other_project_function"]), [])
        await self.idx.remove_project("p1")
        self.assertEqual(self.indexed_paths("p1"), set()); self.assertEqual(self.indexed_paths("p2"), {"src/tax.py"})
        self.assertEqual(self.vec_paths("p2"), {"src/tax.py"})

    async def test_revision_recorded_when_repo_has_commit(self):
        env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
        for a in (["config", "user.name", "t"], ["config", "user.email", "t@t"], ["add", "-A"], ["commit", "-qm", "i"]):
            subprocess.run(["git", "-C", str(self.root), *a], check=True, capture_output=True, env=env)
        await self.idx.index_project(self.ws)
        rev = self.meta._q("SELECT DISTINCT revision FROM rag_files WHERE project_id = 'p1'")
        self.assertEqual(len(rev), 1); self.assertTrue(rev[0][0])


class MetaTests(unittest.TestCase):
    def test_replace_file_is_transactional(self):
        m = make_meta()
        ch = lambda i: Chunk(i, 1, 1, None, "text", f"t{i}")
        m.replace_file("p1", "a.py", "s1", None, 1, [("id1", ch(0)), ("id2", ch(1))], "2026-01-01T00:00:00")
        with self.assertRaises(sqlite3.IntegrityError):                         # id duplicado a mitad de la inserción
            m.replace_file("p1", "a.py", "s2", None, 1, [("id3", ch(0)), ("id3", ch(1))], "2026-01-02T00:00:00")
        self.assertEqual(m.list_files("p1"), {"a.py": "s1"})                   # rollback: el estado anterior sigue intacto
        self.assertEqual(set(m.get_chunks("p1", ["id1", "id2", "id3"])), {"id1", "id2"})

    def test_foreign_keys_and_isolation(self):
        m = make_meta()
        with self.assertRaises(sqlite3.IntegrityError):
            m.replace_file("no-existe", "a.py", "s", None, 1, [], "2026-01-01")
        m.replace_file("p1", "a.py", "s", None, 1, [("id1", Chunk(0, 1, 1, None, "text", "hola mundo"))], "2026-01-01")
        self.assertEqual(m.get_chunks("p2", ["id1"]), {})
        self.assertEqual(m.lexical_candidates("p2", ["hola"]), []); self.assertEqual(len(m.lexical_candidates("p1", ["hola"])), 1)
        self.assertEqual(m.lexical_candidates("p1", ["x'; DROP TABLE rag_chunks;--"]), [])        # términos no alfanuméricos descartados


class RetrieverTests(PipelineBase):
    async def test_hybrid_finds_relevant_chunk_first(self):
        await self.idx.index_project(self.ws)
        res = await self.ret.retrieve("p1", "calculate_tax rate", limit=3)
        self.assertEqual(res.warnings, [])
        self.assertEqual(res.chunks[0].path, "src/tax.py"); self.assertEqual(res.chunks[0].via, "both")

    async def test_isolation_between_projects(self):
        other = tempfile.TemporaryDirectory(); self.addCleanup(other.cleanup)
        (Path(other.name) / "a.py").write_text("def calculate_tax_other(x):\n    return x\n")
        await self.idx.index_project(self.ws); await self.idx.index_project(Workspace(other.name, "p2"))
        for pid, must in (("p1", "src/tax.py"), ("p2", "a.py")):
            res = await self.ret.retrieve(pid, "calculate tax", limit=10)
            self.assertIn(must, {c.path for c in res.chunks})
            self.assertTrue(all(("other" in c.text) == (pid == "p2") for c in res.chunks if "calculate_tax" in c.text))
        with self.assertRaises(ValueError): await self.ret.retrieve("", "x")

    async def test_ollama_down_degrades_to_lexical_with_warning(self):
        await self.idx.index_project(self.ws)
        res = await Retriever(FailingEmbedder(), self.store, self.meta).retrieve("p1", "calculate_tax")
        self.assertTrue(any("semántica no disponible" in w for w in res.warnings))
        self.assertEqual(res.chunks[0].path, "src/tax.py"); self.assertEqual(res.chunks[0].via, "lexical")

    async def test_stale_vector_reference_is_ignored_with_warning(self):
        await self.idx.index_project(self.ws)
        self.meta.delete_file("p1", "src/tax.py")                                  # el vector queda huérfano a propósito
        res = await self.ret.retrieve("p1", "calculate_tax rate")
        self.assertTrue(any("obsoletas" in w for w in res.warnings)); self.assertNotIn("src/tax.py", {c.path for c in res.chunks})

    async def test_neighbors_and_empty_query(self):
        big = "\n".join(f"def func_{i}():\n    return '{'x' * 120}'\n" for i in range(40))
        (self.root / "big.py").write_text(big)
        await self.idx.index_project(self.ws)
        res = await self.ret.retrieve("p1", "func_20", limit=1)
        self.assertGreaterEqual(len(res.chunks), 2); self.assertEqual(res.chunks[1].via, "neighbor")
        self.assertEqual((await self.ret.retrieve("p1", "   ")).chunks, [])

    async def test_format_context_frames_redacts_and_limits(self):
        await self.idx.index_project(self.ws)
        res = await self.ret.retrieve("p1", "calculate_tax")
        res.chunks[0].text += f'\nK = "{FAKE_AWS}"'
        out = format_context(res.chunks, 2000)
        self.assertIn("DATOS no confiables", out); self.assertNotIn(FAKE_AWS, out); self.assertIn("src/tax.py:", out)
        self.assertLessEqual(len(out), 2000); self.assertEqual(format_context([], 100), "")


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.mem = MemoryManager(make_meta(), clock=lambda: self.now)

    async def test_record_recall_and_isolation(self):
        await self.mem.record("p1", "architecture", "El backend usa FastAPI y PostgreSQL", "user")
        await self.mem.record("p1", "decision", "Se eligió Qdrant para vectores")
        await self.mem.record("p2", "note", "Proyecto distinto con FastAPI")
        got = await self.mem.recall("p1", "qdrant vectores")
        self.assertEqual([g["kind"] for g in got], ["decision"])
        self.assertEqual(len(await self.mem.recall("p1", "fastapi")), 1)           # no trae la de p2
        self.assertEqual(len(await self.mem.recall("p1")), 2)
        self.assertIn("[architecture]", await self.mem.summary("p1"))

    async def test_redacts_secrets_and_validates(self):
        mid = await self.mem.record("p1", "note", f'La clave es "{FAKE_AWS}" ojo')
        self.assertNotIn(FAKE_AWS, (await self.mem.recall("p1"))[0]["text"])
        for args in (("", "note", "x"), ("p1", "otro", "x"), ("p1", "note", "  "), ("p1", "note", "x", "root")):
            with self.assertRaises(ValueError, msg=str(args)): await self.mem.record(*args)

    async def test_forget_and_purge_respect_project_and_age(self):
        old = await self.mem.record("p1", "note", "vieja")
        self.now += timedelta(days=40)
        await self.mem.record("p1", "note", "reciente"); other = await self.mem.record("p2", "note", "de otro proyecto")
        self.assertFalse(await self.mem.forget("p1", other))                        # no puede borrar memorias ajenas
        self.assertEqual(await self.mem.purge_older_than("p1", 30), 1)
        self.assertEqual([m["text"] for m in await self.mem.recall("p1")], ["reciente"]); self.assertEqual(len(await self.mem.recall("p2")), 1)
        with self.assertRaises(ValueError): await self.mem.purge_older_than("p1", 0)

    async def test_record_from_agent_events(self):
        self.assertIsNone(await self.mem.record_from_event("p1", {"type": "tool_call", "tool": "read_file"}))
        self.assertIsNone(await self.mem.record_from_event("p1", {"type": "approval_result", "tool": "edit_file", "result": "RECHAZADO por el revisor"}))
        mid = await self.mem.record_from_event("p1", {"type": "approval_result", "tool": "edit_file", "result": "APLICADO: Modificado app.py"})
        self.assertTrue(mid); self.assertEqual((await self.mem.recall("p1"))[0]["kind"], "modification")


if __name__ == "__main__":
    unittest.main()
