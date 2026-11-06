import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api import main


class FakeResponse:
    def __init__(self, ok=True):
        self.is_success = ok


class FakeHttpClient:
    def __init__(self, timeout=3.0, qdrant_ok=True, ollama_ok=True):
        self.qdrant_ok, self.ollama_ok = qdrant_ok, ollama_ok

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        if "/api/tags" in url:
            return FakeResponse(self.ollama_ok)
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


class ApiHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_reports_all_real_dependencies(self):
        with patch.object(main, "engine", FakeEngine()), patch.object(
            main.httpx, "AsyncClient", FakeHttpClient
        ):
            result = await main.health()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result, {"status": "ok"})

    async def test_health_returns_503_when_dependency_is_down(self):
        with patch.object(main, "engine", FakeEngine()), patch.object(
            main.httpx, "AsyncClient",
            lambda timeout=3.0: FakeHttpClient(timeout, qdrant_ok=False)
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.health()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, {"status": "degraded"})
        self.assertNotIn("checks", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
