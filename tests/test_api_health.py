import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api import main


class FakeResponse:
    def __init__(self, ok=True, payload=None):
        self.is_success = ok
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, timeout=3.0, qdrant_ok=True, ollama_ok=True, models=None):
        self.qdrant_ok, self.ollama_ok = qdrant_ok, ollama_ok
        self.models = models if models is not None else [
            {"name": "atomic-code:1.1"},
            {"name": "nomic-embed-text:latest"},
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None):
        if "/api/tags" in url:
            return FakeResponse(self.ollama_ok, {"models": self.models})
        return FakeResponse(self.qdrant_ok)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement):
        return 1


class FakeEngine:
    def connect(self):
        return FakeConnection()


class FailingEngine:
    def connect(self):
        raise RuntimeError("database unavailable")


class ApiHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_reports_all_real_dependencies_and_configured_models(self):
        with patch.object(main, "engine", FakeEngine()), patch.object(
            main.httpx, "AsyncClient", FakeHttpClient
        ), patch.object(main.settings, "redis_cache_enabled", False), patch.object(
            main.settings, "chat_model", "atomic-code:1.1"
        ), patch.object(main.settings, "embed_model", "nomic-embed-text"):
            result = await main.health()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["checks"], {
            "database": "ok", "ollama": "ok", "chat_model": "ok",
            "embedding_model": "ok", "qdrant": "ok"
        })

    async def test_health_returns_503_when_database_connection_fails(self):
        with patch.object(main, "engine", FailingEngine()), patch.object(
            main.httpx, "AsyncClient", FakeHttpClient
        ), patch.object(main.settings, "redis_cache_enabled", False):
            with self.assertRaises(HTTPException) as raised:
                await main.health()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["checks"]["database"], "unavailable")
        self.assertEqual(raised.exception.detail["checks"]["ollama"], "ok")

    async def test_health_marks_models_unavailable_for_malformed_inventory(self):
        with patch.object(main, "engine", FakeEngine()), patch.object(
            main.httpx, "AsyncClient",
            lambda timeout=3.0: FakeHttpClient(timeout, models={"unexpected": "shape"})
        ), patch.object(main.settings, "redis_cache_enabled", False):
            with self.assertRaises(HTTPException) as raised:
                await main.health()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["checks"]["ollama"], "ok")
        self.assertEqual(raised.exception.detail["checks"]["chat_model"], "unavailable")
        self.assertEqual(raised.exception.detail["checks"]["embedding_model"], "unavailable")

    async def test_health_fails_readiness_when_chat_model_is_missing(self):
        with patch.object(main, "engine", FakeEngine()), patch.object(
            main.httpx, "AsyncClient",
            lambda timeout=3.0: FakeHttpClient(timeout, models=[{"name": "nomic-embed-text:latest"}])
        ), patch.object(main.settings, "redis_cache_enabled", False), patch.object(
            main.settings, "chat_model", "atomic-code:1.1"
        ), patch.object(main.settings, "embed_model", "nomic-embed-text"):
            with self.assertRaises(HTTPException) as raised:
                await main.health()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["checks"]["ollama"], "ok")
        self.assertEqual(raised.exception.detail["checks"]["chat_model"], "unavailable")

    async def test_health_returns_503_when_dependency_is_down(self):
        with patch.object(main, "engine", FakeEngine()), patch.object(
            main.httpx, "AsyncClient",
            lambda timeout=3.0: FakeHttpClient(timeout, qdrant_ok=False)
        ), patch.object(main.settings, "redis_cache_enabled", False):
            with self.assertRaises(HTTPException) as raised:
                await main.health()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["status"], "degraded")
        self.assertEqual(raised.exception.detail["checks"]["qdrant"], "unavailable")

    async def test_optional_redis_outage_degrades_but_does_not_fail_health(self):
        with patch.object(main, "engine", FakeEngine()), patch.object(
            main.httpx, "AsyncClient", FakeHttpClient
        ), patch.object(main.settings, "redis_cache_enabled", True), patch.object(
            main, "ping_cache", return_value=False
        ):
            result = await main.health()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["checks"]["redis"], "degraded")
        self.assertEqual(result["checks"]["database"], "ok")

    async def test_liveness_does_not_depend_on_external_services(self):
        self.assertEqual(await main.health_live(), {"status": "alive"})


    async def test_readiness_endpoint_preserves_dependency_failures_as_blocked_503(self):
        failed_health = HTTPException(
            status_code=503,
            detail={"status": "degraded", "checks": {
                "database": "ok", "ollama": "ok", "chat_model": "unavailable",
                "embedding_model": "ok", "qdrant": "ok",
            }},
        )
        auth_report = {"status": "ready", "checks": {"authentication_enabled": True}}
        with patch.object(main, "health", side_effect=failed_health), patch.object(
            main, "auth_readiness", return_value=auth_report
        ):
            response = await main.health_readiness()
        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["checks"], auth_report["checks"])
        self.assertEqual(payload["dependencies"], {
            "database": "ok", "ollama": "ok", "chat_model": "unavailable",
            "embedding_model": "ok", "qdrant": "ok",
        })
        self.assertEqual(payload["optional"], {})

    async def test_readiness_endpoint_allows_optional_redis_degradation(self):
        dependency_health = {"status": "degraded", "checks": {
            "database": "ok", "ollama": "ok", "chat_model": "ok",
            "embedding_model": "ok", "qdrant": "ok", "redis": "degraded",
        }}
        auth_report = {"status": "ready", "checks": {"authentication_enabled": True}}
        with patch.object(main, "health", return_value=dependency_health), patch.object(
            main, "auth_readiness", return_value=auth_report
        ):
            response = await main.health_readiness()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"status":"ready"', response.body)
        self.assertIn(b'"redis":"degraded"', response.body)


if __name__ == "__main__":
    unittest.main()
