import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.schemas import ApprovalRequest, ChatRequest, Message, TaskRequest
from api.workspace_routes import (
    workspace_approve,
    workspace_chat,
    workspace_task,
)


class WorkspaceAuthorizationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_rejects_non_member_before_retrieval_or_model_call(self):
        request = ChatRequest(
            project_id="foreign-project",
            messages=[Message(role="user", content="Lee los archivos")],
        )
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.retrieve", new=AsyncMock()) as retrieve,
            patch("api.workspace_routes.chat", new=AsyncMock()) as chat,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_chat(request, user={"id": "user-a"})
        self.assertEqual(raised.exception.status_code, 404)
        retrieve.assert_not_awaited()
        chat.assert_not_awaited()

    async def test_task_rejects_non_editor_before_planning_or_persisting(self):
        request = TaskRequest(project_id="foreign-project", goal="Analizar el proyecto")
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.create_plan", new=AsyncMock()) as create_plan,
            patch("api.workspace_routes.create_approval") as create_approval,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_task(request, user={"id": "user-a"})
        self.assertEqual(raised.exception.status_code, 404)
        create_plan.assert_not_awaited()
        create_approval.assert_not_called()

    async def test_approval_rejects_non_owner_before_database_write(self):
        request = ApprovalRequest(approved=True, note="Aprobado")
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.engine") as engine,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_approve(
                    "approval-1", request, project_id="foreign-project",
                    user={"id": "user-a"},
                )
        self.assertEqual(raised.exception.status_code, 404)
        engine.begin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
