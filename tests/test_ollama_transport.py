"""Prueba el cliente HTTP contra un servidor local que imita el formato DOCUMENTADO de Ollama.
No prueba contra un Ollama real (no disponible en este entorno)."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.errors import TransportError
from core.ollama_transport import OllamaTransport

STATE = {"fail_next": 0, "last": None}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, json.dumps({"models": [{"name": "qwen2.5-coder:7b-instruct"}]}).encode())
        else:
            self._send(404, b"{}")

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        STATE["last"] = payload
        if payload["model"] == "no-existe":
            return self._send(404, b'{"error":"model not found"}')
        if STATE["fail_next"] > 0:
            STATE["fail_next"] -= 1
            return self._send(503, b"busy")
        if payload["stream"]:
            lines = [{"message": {"content": "ho"}, "done": False}, {"message": {"content": "la"}, "done": False},
                     {"message": {"content": ""}, "done": True, "done_reason": "stop"}]
            return self._send(200, ("\n".join(json.dumps(l) for l in lines) + "\n").encode(), "application/x-ndjson")
        self._send(200, json.dumps({"message": {"role": "assistant", "content": "ok"}, "done": True,
                                    "done_reason": "length", "prompt_eval_count": 11, "eval_count": 7}).encode())


class OllamaTransportTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.t = OllamaTransport(f"http://127.0.0.1:{cls.srv.server_port}", timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    async def test_chat_maps_fields_and_options(self):
        r = await self.t.chat("m", [{"role": "user", "content": "x"}], {"num_ctx": 4096}, "5m")
        self.assertEqual((r.content, r.finish_reason, r.prompt_tokens, r.completion_tokens), ("ok", "length", 11, 7))
        self.assertEqual(STATE["last"]["options"], {"num_ctx": 4096})
        self.assertEqual(STATE["last"]["keep_alive"], "5m")
        self.assertFalse(STATE["last"]["stream"])

    async def test_stream(self):
        self.assertEqual([p async for p in self.t.chat_stream("m", [], {}, "5m")], ["ho", "la"])

    async def test_5xx_is_retryable_404_is_not(self):
        STATE["fail_next"] = 1
        with self.assertRaises(TransportError) as c1:
            await self.t.chat("m", [], {}, "5m")
        self.assertTrue(c1.exception.retryable)
        with self.assertRaises(TransportError) as c2:
            await self.t.chat("no-existe", [], {}, "5m")
        self.assertFalse(c2.exception.retryable)

    async def test_list_models(self):
        self.assertEqual(await self.t.list_models(), {"qwen2.5-coder:7b-instruct"})

    async def test_connection_refused_is_retryable(self):
        with self.assertRaises(TransportError) as c:
            await OllamaTransport("http://127.0.0.1:1", timeout=1).chat("m", [], {}, "5m")
        self.assertTrue(c.exception.retryable)


if __name__ == "__main__":
    unittest.main()
