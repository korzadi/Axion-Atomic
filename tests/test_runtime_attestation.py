import asyncio
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.runtime_attestation import (
    RuntimeAttestationError,
    attest_runtime,
    clear_attestation_cache,
    runtime_attestation_configured,
)

TEMPLATE = "{{ .Prompt }}"
DIGEST = "sha256:" + "b" * 64


def make_settings(**overrides):
    values = {
        "chat_model": "atomic-code:1.1",
        "ollama_base_url": "http://ollama:11434",
        "ollama_request_timeout_seconds": 5.0,
        "billing_runtime_model_digest": DIGEST,
        "billing_runtime_template_sha256": hashlib.sha256(TEMPLATE.encode()).hexdigest(),
        "billing_tokenizer_contract": "qwen2_byte_fallback",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, tags, show):
        self.tags, self.show = tags, show
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        self.requests.append(("GET", url))
        return FakeResponse(self.tags)

    async def post(self, url, json=None):
        self.requests.append(("POST", url))
        return FakeResponse(self.show)


def run(settings, tags, show):
    client = FakeClient(tags, show)
    with patch("api.runtime_attestation.httpx.AsyncClient", lambda timeout: client):
        result = asyncio.run(attest_runtime(settings))
    return result, client


class RuntimeAttestationTests(unittest.TestCase):
    def setUp(self):
        clear_attestation_cache()

    def test_manifest_requires_digest_template_and_supported_contract(self):
        self.assertTrue(runtime_attestation_configured(make_settings()))
        self.assertFalse(runtime_attestation_configured(make_settings(billing_runtime_model_digest=None)))
        self.assertFalse(runtime_attestation_configured(make_settings(billing_runtime_template_sha256="short")))
        self.assertFalse(runtime_attestation_configured(make_settings(billing_tokenizer_contract="unknown")))

    def test_attests_exact_digest_template_and_architecture(self):
        tags = {"models": [{"name": "atomic-code:1.1", "digest": DIGEST}]}
        show = {"template": TEMPLATE, "model_info": {"general.architecture": "qwen2"}}
        identity, client = run(make_settings(), tags, show)
        self.assertEqual(identity.runtime_model, "atomic-code:1.1")
        self.assertEqual(identity.model_digest, DIGEST)
        self.assertEqual(identity.tokenizer_contract, "qwen2_byte_fallback")
        self.assertEqual(len(client.requests), 2)

    def test_rejects_digest_mismatch(self):
        tags = {"models": [{"name": "atomic-code:1.1", "digest": "sha256:" + "c" * 64}]}
        show = {"template": TEMPLATE, "model_info": {"general.architecture": "qwen2"}}
        with self.assertRaises(RuntimeAttestationError):
            run(make_settings(), tags, show)

    def test_rejects_template_mismatch(self):
        tags = {"models": [{"name": "atomic-code:1.1", "digest": DIGEST}]}
        show = {"template": "different", "model_info": {"general.architecture": "qwen2"}}
        with self.assertRaises(RuntimeAttestationError):
            run(make_settings(), tags, show)

    def test_rejects_architecture_mismatch(self):
        tags = {"models": [{"name": "atomic-code:1.1", "digest": DIGEST}]}
        show = {"template": TEMPLATE, "model_info": {"general.architecture": "llama"}}
        with self.assertRaises(RuntimeAttestationError):
            run(make_settings(), tags, show)

    def test_rejects_missing_model_without_calling_show(self):
        tags = {"models": [{"name": "another-model:latest", "digest": DIGEST}]}
        client = FakeClient(tags, {})
        with patch("api.runtime_attestation.httpx.AsyncClient", lambda timeout: client):
            with self.assertRaises(RuntimeAttestationError):
                asyncio.run(attest_runtime(make_settings()))
        self.assertEqual(client.requests, [("GET", "http://ollama:11434/api/tags")])

    def test_missing_manifest_fails_before_any_network_call(self):
        client = FakeClient({}, {})
        with patch("api.runtime_attestation.httpx.AsyncClient", lambda timeout: client):
            with self.assertRaises(RuntimeAttestationError):
                asyncio.run(attest_runtime(make_settings(billing_runtime_model_digest=None)))
        self.assertEqual(client.requests, [])

    def test_success_is_cached_briefly(self):
        tags = {"models": [{"name": "atomic-code:1.1", "digest": DIGEST}]}
        show = {"template": TEMPLATE, "model_info": {"general.architecture": "qwen2"}}
        settings = make_settings()
        _, first = run(settings, tags, show)
        _, second = run(settings, tags, show)
        self.assertEqual(len(first.requests), 2)
        self.assertEqual(len(second.requests), 0)


if __name__ == "__main__":
    unittest.main()
