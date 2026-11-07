"""Regression test: the legacy API must stay gated at the actual HTTP route."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import main
from api.config import settings


class LegacyApiRouteGateTests(unittest.TestCase):
    def test_legacy_chat_route_is_disabled_even_with_a_valid_api_key(self):
        secret = "ci-only-legacy-key-that-is-long-enough-0123456789"
        payload = {
            "model": "atomic-code",
            "project_id": "project-legacy-test",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.2,
            "max_tokens": 64,
            "stream": False,
        }
        with (
            patch.object(settings, "legacy_api_enabled", False),
            patch.object(settings, "api_key", secret),
            patch.object(main, "retrieve") as retrieve,
            patch.object(main, "chat") as chat,
            TestClient(main.app) as client,
        ):
            response = client.post(
                "/v1/chat/completions",
                json=payload,
                headers={"X-API-Key": secret},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Legacy API is disabled")
        retrieve.assert_not_called()
        chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
