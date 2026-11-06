import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from api.workspace_routes import workspace_run_detail, workspace_runs


class WorkspaceRunRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        admission = patch("api.workspace_routes._enforce_workspace_limit")
        admission.start()
        self.addCleanup(admission.stop)

    async def test_list_is_scoped_to_authorized_project(self):
        rows = [{"id": "run-1", "goal": "Review", "status": "done"}]
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.all.return_value = rows
        engine_context = MagicMock()
        engine_context.__enter__.return_value = conn
        with patch("api.workspace_routes.authorize_project", return_value="viewer") as authorize, \
             patch("api.workspace_routes.engine.connect", return_value=engine_context):
            result = await workspace_runs(project_id="project-a", limit=10, user={"id": "user-a"})
        self.assertEqual(result["items"], rows)
        authorize.assert_called_once_with("user-a", "project-a", ("owner", "admin", "editor", "viewer"))
        params = conn.execute.call_args.args[1]
        self.assertEqual(params, {"project_id": "project-a", "limit": 10})

    async def test_detail_parses_snapshot_and_scopes_both_ids(self):
        row = {
            "id": "run-a", "project_id": "project-a", "goal": "Review",
            "messages": '[{"role":"user","content":"hello"}]',
            "pending_actions": "[]",
        }
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = row
        engine_context = MagicMock()
        engine_context.__enter__.return_value = conn
        with patch("api.workspace_routes.authorize_project", return_value="viewer") as authorize, \
             patch("api.workspace_routes.engine.connect", return_value=engine_context):
            result = await workspace_run_detail(run_id="run-a", project_id="project-a", user={"id": "user-a"})
        self.assertEqual(result["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(result["pending_actions"], [])
        authorize.assert_called_once_with("user-a", "project-a", ("owner", "admin", "editor", "viewer"))
        self.assertEqual(conn.execute.call_args.args[1], {"run_id": "run-a", "project_id": "project-a"})

    async def test_detail_does_not_disclose_run_from_other_project(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = None
        engine_context = MagicMock()
        engine_context.__enter__.return_value = conn
        with patch("api.workspace_routes.authorize_project", return_value="viewer"), \
             patch("api.workspace_routes.engine.connect", return_value=engine_context):
            with self.assertRaises(HTTPException) as raised:
                await workspace_run_detail(run_id="run-a", project_id="project-b", user={"id": "user-b"})
        self.assertEqual(raised.exception.status_code, 404)

    async def test_invalid_snapshot_fails_closed(self):
        row = {
            "id": "run-a", "project_id": "project-a", "goal": "Review",
            "messages": "not-json", "pending_actions": "[]",
        }
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = row
        engine_context = MagicMock()
        engine_context.__enter__.return_value = conn
        with patch("api.workspace_routes.authorize_project", return_value="viewer"), \
             patch("api.workspace_routes.engine.connect", return_value=engine_context):
            with self.assertRaises(HTTPException) as raised:
                await workspace_run_detail(run_id="run-a", project_id="project-a", user={"id": "user-a"})
        self.assertEqual(raised.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()
