import unittest
from unittest.mock import AsyncMock, patch

from api.ollama import InferenceResult
from api.schemas import ChatRequest, Message
from api.workspace_routes import workspace_chat
from api.main import completions


class ModelIdentityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request = ChatRequest(
            project_id="project-test",
            messages=[Message(role="user", content="Hola")],
        )

    async def test_workspace_chat_reports_public_catalog_model(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes.retrieve", new=AsyncMock(return_value="")),
            patch("api.workspace_routes.chat_with_usage", new=AsyncMock(return_value=InferenceResult(content="Respuesta", requested_model="atomic-code:test", returned_model="atomic-code:test", done=True, prompt_eval_count=1, eval_count=1, total_duration_ns=1, load_duration_ns=None, prompt_eval_duration_ns=None, eval_duration_ns=None, usage_source="ollama_response"))),
            patch("api.workspace_routes.settings.chat_model", "atomic-code:test"),
        ):
            response = await workspace_chat(self.request, user={"id": "user-test"})
        self.assertEqual(response["model"], "atomic-code")

    async def test_workspace_chat_rejects_unexpected_runtime_model(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes.retrieve", new=AsyncMock(return_value="")),
            patch("api.workspace_routes.chat_with_usage", new=AsyncMock(return_value=InferenceResult(content="Respuesta", requested_model="atomic-code:test", returned_model="different-model", done=True, prompt_eval_count=1, eval_count=1, total_duration_ns=1, load_duration_ns=None, prompt_eval_duration_ns=None, eval_duration_ns=None, usage_source="ollama_response"))),
            patch("api.workspace_routes.settings.chat_model", "atomic-code:test"),
        ):
            with self.assertRaises(Exception) as raised:
                await workspace_chat(self.request, user={"id": "user-test"})
        self.assertEqual(getattr(raised.exception, "status_code", None), 503)

    async def test_legacy_chat_reports_configured_model(self):
        with (
            patch("api.main.retrieve", new=AsyncMock(return_value="")),
            patch("api.main.chat", new=AsyncMock(return_value="Respuesta")),
            patch("api.main.settings.chat_model", "atomic-code:test"),
        ):
            response = await completions(self.request)
        self.assertEqual(response["model"], "atomic-code:test")


if __name__ == "__main__":
    unittest.main()
