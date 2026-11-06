import unittest
from unittest.mock import AsyncMock, patch

from api.schemas import ChatRequest, Message
from api.workspace_routes import workspace_chat
from api.main import completions


class ModelIdentityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request = ChatRequest(
            project_id="project-test",
            messages=[Message(role="user", content="Hola")],
        )

    async def test_workspace_chat_reports_configured_model(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes.retrieve", new=AsyncMock(return_value="")),
            patch("api.workspace_routes.chat", new=AsyncMock(return_value="Respuesta")),
            patch("api.workspace_routes.settings.chat_model", "atomic-code:test"),
        ):
            response = await workspace_chat(self.request, user={"id": "user-test"})
        self.assertEqual(response["model"], "atomic-code:test")

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
