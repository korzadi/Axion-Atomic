"""Pruebas HTTP unitarias para el arranque y la reanudación del runtime persistente."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.schemas import TaskRequest
from api.workspace_routes import workspace_agent_resume, workspace_agent_start


class WorkspaceAgentRuntimeHttpTests(unittest.IsolatedAsyncioTestCase):
    def _run(self, status="done"):
        return SimpleNamespace(
            id="run-123", project_id="project-a", goal="Revisar proyecto",
            status=status, final="Resultado", error=None, steps=2,
            pending=[SimpleNamespace(
                proposal_id="approval-1", tool="write_file",
                action_hash="hash-1", summary="Actualizar un archivo",
            )] if status == "awaiting_approval" else [],
        )

    async def test_start_calls_persistent_runtime_and_returns_safe_action_summary(self):
        run = self._run("awaiting_approval")
        runtime = SimpleNamespace(start=AsyncMock(return_value=run))
        with patch("api.workspace_routes._agent_runtime", return_value=runtime):
            result = await workspace_agent_start(
                TaskRequest(project_id="project-a", goal="Revisar proyecto"),
                user={"id": "user-a"},
            )

        runtime.start.assert_awaited_once_with(
            {"id": "user-a"}, "project-a", "Revisar proyecto"
        )
        self.assertEqual(result["run_id"], "run-123")
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertEqual(result["pending_actions"], [{
            "proposal_id": "approval-1", "tool": "write_file",
            "action_hash": "hash-1", "summary": "Actualizar un archivo",
        }])
        self.assertNotIn("args", result["pending_actions"][0])

    async def test_resume_is_scoped_to_user_project_and_run(self):
        run = self._run("done")
        runtime = SimpleNamespace(resume=AsyncMock(return_value=run))
        with patch("api.workspace_routes._agent_runtime", return_value=runtime):
            result = await workspace_agent_resume(
                "run-123", project_id="project-a", user={"id": "user-a"}
            )

        runtime.resume.assert_awaited_once_with(
            {"id": "user-a"}, "project-a", "run-123"
        )
        self.assertEqual(result["status"], "done")

    async def test_invalid_goal_is_returned_as_422(self):
        runtime = SimpleNamespace(start=AsyncMock(side_effect=ValueError("goal es obligatorio")))
        with patch("api.workspace_routes._agent_runtime", return_value=runtime):
            with self.assertRaises(HTTPException) as raised:
                await workspace_agent_start(
                    TaskRequest(project_id="project-a", goal="valid goal"),
                    user={"id": "user-a"},
                )
        self.assertEqual(raised.exception.status_code, 422)

    async def test_unavailable_workspace_fails_closed(self):
        runtime = SimpleNamespace(start=AsyncMock(side_effect=OSError("private path")))
        with patch("api.workspace_routes._agent_runtime", return_value=runtime):
            with self.assertRaises(HTTPException) as raised:
                await workspace_agent_start(
                    TaskRequest(project_id="project-a", goal="valid goal"),
                    user={"id": "user-a"},
                )
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("private path", raised.exception.detail)


    async def test_start_and_resume_routes_require_csrf_dependency(self):
        import inspect
        from api.workspace_routes import workspace_agent_resume, workspace_agent_start

        start_user = inspect.signature(workspace_agent_start).parameters["user"].default
        resume_user = inspect.signature(workspace_agent_resume).parameters["user"].default
        self.assertEqual(start_user.dependency.__name__, "_csrf_user")
        self.assertEqual(resume_user.dependency.__name__, "_csrf_user")


if __name__ == "__main__":
    unittest.main()

