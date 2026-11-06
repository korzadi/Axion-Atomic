import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from agent.project_runtime import ProjectAgentRuntime


class ProjectAgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self):
        return ProjectAgentRuntime(
            engine=object(),
            chat=AsyncMock(),
            workspace_root="/private/workspaces",
        )

    async def test_start_authorizes_and_composes_before_agent_run(self):
        runtime = self._runtime()
        agent = SimpleNamespace(run=AsyncMock(return_value="run-result"))
        with patch("agent.project_runtime.build_authorized_project_toolset", return_value=(object(), {})) as compose, \
             patch("agent.project_runtime.build_coding_agent_from_engine", return_value=agent) as factory:
            result = await runtime.start({"id": "user-1"}, "project-1", "  Inspeccionar  ", "contexto")

        self.assertEqual(result, "run-result")
        compose.assert_called_once()
        self.assertEqual(compose.call_args.args, ({"id": "user-1"}, "project-1"))
        factory.assert_called_once()
        agent.run.assert_awaited_once_with("Inspeccionar", context="contexto", project_id="project-1")

    async def test_authorization_failure_stops_agent_construction(self):
        runtime = self._runtime()
        with patch("agent.project_runtime.build_authorized_project_toolset", side_effect=PermissionError("denegado")), \
             patch("agent.project_runtime.build_coding_agent_from_engine") as factory:
            with self.assertRaises(PermissionError):
                await runtime.start({"id": "user-2"}, "project-1", "Inspeccionar")
        factory.assert_not_called()

    async def test_resume_restores_using_the_requested_project_scope(self):
        runtime = self._runtime()
        restored = SimpleNamespace(status="needs_reconciliation")
        agent = SimpleNamespace(restore=lambda run_id, project_id: restored,
                                resume=AsyncMock(), continue_run=AsyncMock())
        with patch("agent.project_runtime.build_authorized_project_toolset", return_value=(object(), {})), \
             patch("agent.project_runtime.build_coding_agent_from_engine", return_value=agent):
            result = await runtime.resume({"id": "user-1"}, "project-1", "run-1")

        self.assertIs(result, restored)
        agent.resume.assert_not_awaited()
        agent.continue_run.assert_not_awaited()

    async def test_resume_delegates_approval_waiting_run_to_approval_gate(self):
        runtime = self._runtime()
        restored = SimpleNamespace(status="awaiting_approval")
        agent = SimpleNamespace(
            restore=Mock(return_value=restored),
            resume=AsyncMock(return_value="resumed"),
            continue_run=AsyncMock(),
        )
        with patch("agent.project_runtime.build_authorized_project_toolset", return_value=(object(), {})), \
             patch("agent.project_runtime.build_coding_agent_from_engine", return_value=agent):
            result = await runtime.resume({"id": "user-1"}, "project-1", " run-1 ")

        self.assertEqual(result, "resumed")
        agent.restore.assert_called_once_with("run-1", "project-1")
        agent.resume.assert_awaited_once_with(restored)
        agent.continue_run.assert_not_awaited()

    async def test_resume_continues_only_a_safe_running_state(self):
        runtime = self._runtime()
        restored = SimpleNamespace(status="running")
        agent = SimpleNamespace(restore=lambda run_id, project_id: restored,
                                resume=AsyncMock(), continue_run=AsyncMock(return_value="continued"))
        with patch("agent.project_runtime.build_authorized_project_toolset", return_value=(object(), {})), \
             patch("agent.project_runtime.build_coding_agent_from_engine", return_value=agent):
            result = await runtime.resume({"id": "user-1"}, "project-1", "run-1")

        self.assertEqual(result, "continued")
        agent.continue_run.assert_awaited_once_with(restored)

    async def test_empty_goal_is_rejected_before_workspace_resolution(self):
        runtime = self._runtime()
        with patch("agent.project_runtime.build_authorized_project_toolset") as compose:
            with self.assertRaisesRegex(ValueError, "goal es obligatorio"):
                await runtime.start({"id": "user-1"}, "project-1", "  ")
        compose.assert_not_called()


if __name__ == "__main__":
    unittest.main()
