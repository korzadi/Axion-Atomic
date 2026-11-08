"""Qdrant/Ollama simulados con servidores HTTP locales que siguen la API REST DOCUMENTADA.
Verifican nuestras peticiones y el aislamiento por proyecto; NO prueban contra Qdrant/Ollama reales."""
import json
import math
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.errors import TransportError
from core.ollama_transport import OllamaTransport
from rag.embedder import OllamaEmbedder
from rag.store import Hit, InMemoryVectorStore, Point, QdrantStore, StoreConfigError

S = {"cols": {}, "headers": [], "requests": []}


def match(payload, flt):
    return all(payload.get(m["key"]) == m["match"]["value"] for m in flt["must"])


class Q(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)

    def _handle(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        S["headers"].append(self.headers.get("api-key")); S["requests"].append((method, self.path, body))
        if self.path.startswith("/api/embed"):
            return self._send(200, {"embeddings": [[0.5, 0.5, 0.5, 0.5] if "mal" not in t else [1.0] for t in body["input"]]})
        m = re.match(r"^/collections/([^/?]+)(/[^?]*)?(\?.*)?$", self.path)
        name, sub = m.group(1), m.group(2) or ""
        col = S["cols"].get(name)
        if sub == "" and method == "GET":
            return self._send(200, {"result": {"config": {"params": {"vectors": {"size": col["dim"], "distance": "Cosine"}}}}}) if col else self._send(404, {"status": {"error": "Not found"}})
        if sub == "" and method == "PUT":
            S["cols"][name] = {"dim": body["vectors"]["size"], "points": {}, "indexes": []}; return self._send(200, {"result": True})
        if col is None:
            return self._send(404, {})
        if sub == "/index":
            col["indexes"].append(body["field_name"]); return self._send(200, {"result": {}})
        if sub == "/points" and method == "PUT":
            for p in body["points"]:
                if len(p["vector"]) != col["dim"]:
                    return self._send(400, {"error": "bad dim"})
                col["points"][p["id"]] = p
            return self._send(200, {"result": {"status": "completed"}})
        if sub == "/points/delete":
            if "points" in body:
                ids = set(body["points"])
                col["points"] = {key: point for key, point in col["points"].items() if key not in ids}
            else:
                col["points"] = {k: p for k, p in col["points"].items() if not match(p["payload"], body["filter"])}
            return self._send(200, {"result": {}})
        if sub == "/points/search":
            def cos(a, b):
                na, nb = math.sqrt(sum(x * x for x in a)) or 1, math.sqrt(sum(x * x for x in b)) or 1
                return sum(x * y for x, y in zip(a, b)) / (na * nb)
            hits = [{"id": p["id"], "score": cos(body["vector"], p["vector"]), "payload": p["payload"]}
                    for p in col["points"].values() if match(p["payload"], body["filter"])]
            return self._send(200, {"result": sorted(hits, key=lambda h: -h["score"])[:body["limit"]]})
        self._send(404, {})

    def do_GET(self): self._handle("GET")
    def do_PUT(self): self._handle("PUT")
    def do_POST(self): self._handle("POST")


class Base(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Q); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()

    def setUp(self): S["cols"].clear(); S["headers"].clear(); S["requests"].clear()


class QdrantTests(Base):
    def pts(self):
        return [Point("a", [1, 0, 0, 0], {"project_id": "p1", "path": "x.py"}), Point("b", [0, 1, 0, 0], {"project_id": "p1", "path": "y.py"}),
                Point("c", [1, 0, 0, 0], {"project_id": "p2", "path": "x.py"})]

    async def test_ensure_creates_collection_and_indexes_once(self):
        st = QdrantStore(self.url, "col", 4, api_key="k")
        await st.ensure(); await st.ensure()
        self.assertEqual(S["cols"]["col"]["dim"], 4)
        self.assertEqual({"project_id", "path"}, set(S["cols"]["col"]["indexes"]))
        self.assertEqual(sum(1 for r in S["requests"] if r[0] == "PUT" and r[1] == "/collections/col"), 1)
        self.assertTrue(all(h == "k" for h in S["headers"]))

    async def test_dimension_mismatch_fails_without_touching_data(self):
        await QdrantStore(self.url, "col", 4).ensure()
        S["cols"]["col"]["points"]["z"] = {"id": "z", "vector": [0] * 4, "payload": {"project_id": "p1", "path": "q"}}
        with self.assertRaises(StoreConfigError): await QdrantStore(self.url, "col", 8).ensure()
        self.assertIn("z", S["cols"]["col"]["points"])
        self.assertFalse(any(r[0] == "DELETE" or "delete" in r[1] for r in S["requests"]))

    async def test_search_is_always_project_filtered(self):
        st = QdrantStore(self.url, "col", 4); await st.ensure(); await st.upsert(self.pts())
        hits = await st.search("p1", [1, 0, 0, 0], 10)
        self.assertEqual([h.id for h in hits], ["a", "b"])                      # 'c' es de p2
        search_req = [r for r in S["requests"] if r[1].endswith("/points/search")][0][2]
        self.assertEqual(search_req["filter"]["must"][0], {"key": "project_id", "match": {"value": "p1"}})
        for bad in ("", None):
            with self.assertRaises(ValueError): await st.search(bad, [1, 0, 0, 0], 5)

    async def test_delete_path_and_project_scoped(self):
        st = QdrantStore(self.url, "col", 4); await st.ensure(); await st.upsert(self.pts())
        await st.delete_path("p1", "x.py")
        self.assertEqual(set(S["cols"]["col"]["points"]), {"b", "c"})            # no toca p2/x.py
        await st.delete_project("p1")
        self.assertEqual(set(S["cols"]["col"]["points"]), {"c"})
        with self.assertRaises(ValueError): await st.delete_project("")

    async def test_delete_ids_removes_only_superseded_points(self):
        st = QdrantStore(self.url, "col", 4); await st.ensure(); await st.upsert(self.pts())
        await st.delete_ids(["a", "c"])
        self.assertEqual(set(S["cols"]["col"]["points"]), {"b"})
        request = [r for r in S["requests"] if r[1].endswith("/points/delete")][-1]
        self.assertEqual(request[2], {"points": ["a", "c"]})

    async def test_upsert_requires_complete_payload_before_any_http_write(self):
        st = QdrantStore(self.url, "col", 4); await st.ensure()
        writes_before = sum(1 for request in S["requests"] if request[0] == "PUT" and "/points" in request[1])
        invalid_payloads = (
            {"path": "x.py"},
            {"project_id": "p1"},
            {"project_id": " ", "path": "x.py"},
            {"project_id": "p1", "path": ""},
            {"project_id": 7, "path": "x.py"},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                await st.upsert([Point("bad", [1, 0, 0, 0], payload)])
        # Un lote >64 con un elemento inválido tampoco debe publicar el primer batch.
        batch = self.pts() * 22
        batch[-1] = Point("invalid-last", [1, 0, 0, 0], {"project_id": "p1"})
        with self.assertRaises(ValueError):
            await st.upsert(batch)
        writes_after = sum(1 for request in S["requests"] if request[0] == "PUT" and "/points" in request[1])
        self.assertEqual(writes_after, writes_before)
        with self.assertRaises(TransportError):
            await st.upsert([Point("bad-dimension", [1, 0], {"project_id": "p1", "path": "x.py"})])
        with self.assertRaises(TransportError):
            await QdrantStore("http://127.0.0.1:1", "c", 4, timeout=1).ensure()


class InMemoryStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_isolation_and_delete(self):
        st = InMemoryVectorStore()
        await st.upsert(QdrantTests.pts(None))
        self.assertEqual({h.id for h in await st.search("p1", [1, 0, 0, 0], 5)}, {"a", "b"})
        await st.delete_path("p1", "x.py")
        self.assertEqual({h.id for h in await st.search("p1", [1, 0, 0, 0], 5)}, {"b"})
        with self.assertRaises(ValueError): await st.search("", [1], 1)

    async def test_upsert_validates_entire_batch_before_mutation(self):
        st = InMemoryVectorStore()
        valid = Point("valid", [1, 0, 0, 0], {"project_id": "p1", "path": "ok.py"})
        invalid = Point("invalid", [1, 0, 0, 0], {"project_id": "p1"})
        with self.assertRaises(ValueError):
            await st.upsert([valid, invalid])
        self.assertEqual(st.points, {})

    async def test_delete_ids_removes_only_requested_points(self):
        st = InMemoryVectorStore()
        await st.upsert(QdrantTests.pts(None))
        await st.delete_ids(["a", "c"])
        self.assertEqual(set(st.points), {"b"})


class EmbedderTests(Base):
    async def test_batches_and_validates_dimension(self):
        emb = OllamaEmbedder(OllamaTransport(self.url, timeout=5), "nomic", 4, batch_size=2)
        vecs = await emb.embed(["a", "b", "c", "d", "e"])
        self.assertEqual(len(vecs), 5)
        self.assertEqual(sum(1 for r in S["requests"] if r[1] == "/api/embed"), 3)     # 2+2+1
        with self.assertRaises(TransportError): await emb.embed(["mal"])                  # dimensión 1 != 4


if __name__ == "__main__":
    unittest.main()
