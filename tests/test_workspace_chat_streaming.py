import json
import unittest
from types import SimpleNamespace

from fastapi.responses import StreamingResponse

from api.schemas import ChatRequest, Message
import api.billing_result_crypto as brc
import api.workspace_routes as ws
from api.runtime_attestation import RuntimeIdentity

IDENTITY = RuntimeIdentity(
    runtime_model="atomic-code:1.1",
    model_digest="sha256:" + "b" * 64,
    template_sha256="a" * 64,
    tokenizer_contract="qwen2_byte_fallback",
)


def _request(stream=True):
    return ChatRequest(project_id="project-a", messages=[Message(role="user", content="Hola")], max_tokens=64, stream=stream)


def _inference(text="Hola mundo", prompt=5, output=2):
    return SimpleNamespace(
        content=text, requested_model="atomic-code:1.1", returned_model="atomic-code:1.1",
        prompt_eval_count=prompt, eval_count=output, usage_source="ollama_response", done=True,
    )


async def _collect_sse(response):
    body = b""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, (bytes, bytearray)) else chunk.encode()
    events = []
    for frame in body.decode().split("\n\n"):
        if not frame.strip():
            continue
        event = "message"
        data = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            events.append((event, json.loads("\n".join(data))))
    return events


class WorkspaceChatStreamingTests(unittest.IsolatedAsyncioTestCase):
    def _patch_common(self, *, billing=False):
        async def _retrieve(*a, **k): return ""
        async def _attest(*a, **k): return IDENTITY
        self._orig = {
            "role": ws._project_role, "limit": ws._enforce_workspace_limit, "retrieve": ws.retrieve,
            "stream": ws._chat_with_usage_stream, "chat": ws.chat_with_usage,
            "save": ws._save_chat_history, "shadow": ws.persist_shadow_usage_event,
            "billing": ws.settings.billing_enforcement_enabled, "model": ws.settings.chat_model,
            "iw": ws.settings.billing_input_credit_weight, "ow": ws.settings.billing_output_credit_weight,
            "attest": ws.attest_runtime, "keyprov": ws.EnvironmentResultKeyProvider,
            "exec": ws.execute_durable_reserved_inference, "brc_key": brc.EnvironmentResultKeyProvider.active_key,
        }
        ws._project_role = lambda *a, **k: ("owner",)
        ws._enforce_workspace_limit = lambda *a, **k: None
        ws.retrieve = _retrieve
        ws._save_chat_history = lambda *a, **k: None
        ws.persist_shadow_usage_event = lambda *a, **k: None
        ws.settings.billing_enforcement_enabled = billing
        ws.settings.chat_model = "atomic-code:1.1"
        ws.settings.billing_input_credit_weight = 1
        ws.settings.billing_output_credit_weight = 1
        ws.attest_runtime = _attest
        ws.EnvironmentResultKeyProvider = type("K", (), {"active_key": lambda self: ("k", b"x" * 32)})
        brc.EnvironmentResultKeyProvider.active_key = lambda self: ("k", b"x" * 32)

    def _restore(self):
        o = self._orig
        ws._project_role, ws._enforce_workspace_limit, ws.retrieve = o["role"], o["limit"], o["retrieve"]
        ws._chat_with_usage_stream, ws.chat_with_usage = o["stream"], o["chat"]
        ws._save_chat_history, ws.persist_shadow_usage_event = o["save"], o["shadow"]
        ws.settings.billing_enforcement_enabled, ws.settings.chat_model = o["billing"], o["model"]
        ws.settings.billing_input_credit_weight, ws.settings.billing_output_credit_weight = o["iw"], o["ow"]
        ws.attest_runtime, ws.EnvironmentResultKeyProvider = o["attest"], o["keyprov"]
        ws.execute_durable_reserved_inference = o["exec"]
        brc.EnvironmentResultKeyProvider.active_key = o["brc_key"]

    async def test_stream_false_preserves_json_contract(self):
        self._patch_common(billing=False)
        try:
            async def _chat(*a, **k): return _inference()
            ws.chat_with_usage = _chat
            response = await ws.workspace_chat(_request(stream=False), {"id": "user-a"})
        finally:
            self._restore()
        self.assertIsInstance(response, dict)
        self.assertEqual(response["choices"][0]["message"]["content"], "Hola mundo")
        self.assertEqual(response["usage_billing"]["mode"], "shadow")

    async def test_stream_true_emits_sse_deltas_and_done_without_billing(self):
        self._patch_common(billing=False)
        try:
            async def _stream(*a, **k):
                yield {"type": "delta", "content": "Hola"}
                yield {"type": "delta", "content": " mundo"}
                yield {"type": "done", "result": _inference("Hola mundo")}
            ws._chat_with_usage_stream = _stream
            response = await ws.workspace_chat(_request(stream=True), {"id": "user-a"})
            self.assertIsInstance(response, StreamingResponse)
            self.assertIn("text/event-stream", response.media_type)
            events = await _collect_sse(response)
        finally:
            self._restore()
        self.assertEqual([e for e, _ in events], ["message", "message", "done"])
        self.assertEqual("".join(d["delta"] for e, d in events if e == "message"), "Hola mundo")
        self.assertEqual(events[-1][1]["usage_billing"]["mode"], "shadow")

    async def test_stream_true_rejects_model_mismatch(self):
        self._patch_common(billing=False)
        try:
            bad = _inference(); bad.returned_model = "other:1"
            async def _stream(*a, **k):
                yield {"type": "delta", "content": "x"}
                yield {"type": "done", "result": bad}
            ws._chat_with_usage_stream = _stream
            response = await ws.workspace_chat(_request(stream=True), {"id": "user-a"})
            events = await _collect_sse(response)
        finally:
            self._restore()
        self.assertEqual([d for e, d in events if e == "error"][0]["status_code"], 503)

    async def test_stream_true_with_billing_settles_and_emits_done(self):
        self._patch_common(billing=True)
        durable = SimpleNamespace(
            inference=_inference(),
            reservation=SimpleNamespace(reservation_id="00000000-0000-0000-0000-000000000001"),
            settlement=SimpleNamespace(state="settled", charged_credits=7),
            recovered=False, execution_id="00000000-0000-0000-0000-000000000002",
        )
        called = {}
        try:
            async def _stream(*a, **k):
                yield {"type": "delta", "content": "Hola"}
                yield {"type": "done", "result": _inference()}
            ws._chat_with_usage_stream = _stream
            async def execute(*a, **k): called["ok"] = True; return durable
            ws.execute_durable_reserved_inference = execute
            response = await ws.workspace_chat(_request(stream=True), {"id": "user-a"}, idempotency_key_header="k-1")
            events = await _collect_sse(response)
        finally:
            self._restore()
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(events[-1][1]["usage_billing"]["mode"], "ledger")
        self.assertTrue(called.get("ok"))

    async def test_stream_true_billing_insufficient_credits_emits_error(self):
        from api.billing_policy import InsufficientCredits
        self._patch_common(billing=True)
        try:
            async def _stream(*a, **k):
                yield {"type": "done", "result": _inference()}
            ws._chat_with_usage_stream = _stream
            async def execute(*a, **k): raise InsufficientCredits("no")
            ws.execute_durable_reserved_inference = execute
            response = await ws.workspace_chat(_request(stream=True), {"id": "user-a"}, idempotency_key_header="k-2")
            events = await _collect_sse(response)
        finally:
            self._restore()
        self.assertEqual([d for e, d in events if e == "error"][0]["status_code"], 402)


if __name__ == "__main__":
    unittest.main()
