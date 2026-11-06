import unittest
from unittest.mock import MagicMock, patch

from api.schemas import ApprovalRequest
from api.workspace_routes import workspace_approvals, workspace_decide_plan_approval


class WorkspacePlanApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_returns_plan_and_action_approvals_separately(self):
        action_rows = [{"id": "action-1", "state": "pending"}]
        plan_rows = [{"id": 7, "project_id": "project-a", "goal": "Inspect", "status": "pending"}]
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.all.side_effect = [action_rows, plan_rows]
        engine_context = MagicMock()
        engine_context.__enter__.return_value = conn
        with patch("api.workspace_routes.authorize_project", return_value="editor") as authorize, \
             patch("api.workspace_routes.engine.connect", return_value=engine_context):
            result = await workspace_approvals(project_id="project-a", user={"id": "user-a"})
        self.assertEqual(result["items"], action_rows)
        self.assertEqual(result["plan_items"], plan_rows)
        authorize.assert_called_once_with("user-a", "project-a", ("owner", "admin", "editor"))

    async def test_plan_decision_uses_session_identity_and_project_scope(self):
        conn = MagicMock()
        conn.execute.return_value.first.return_value = (7,)
        tx = MagicMock()
        tx.__enter__.return_value = conn
        with patch("api.workspace_routes.authorize_project", return_value="owner") as authorize, \
             patch("api.workspace_routes.engine.begin", return_value=tx):
            result = await workspace_decide_plan_approval(
                approval_id=7,
                req=ApprovalRequest(approved=True, note="Reviewed"),
                project_id="project-a",
                user={"id": "user-owner"},
            )
        self.assertEqual(result, {
            "id": 7, "project_id": "project-a", "status": "approved", "execution": "not_executed"
        })
        authorize.assert_called_once_with("user-owner", "project-a", ("owner", "admin"))
        params = conn.execute.call_args.args[1]
        self.assertEqual(params["reviewer"], "user-owner")
        self.assertEqual(params["project_id"], "project-a")
        self.assertEqual(params["approval_id"], 7)

    async def test_plan_decision_does_not_accept_missing_or_resolved_id(self):
        conn = MagicMock()
        conn.execute.return_value.first.return_value = None
        tx = MagicMock()
        tx.__enter__.return_value = conn
        with patch("api.workspace_routes.authorize_project", return_value="admin"), \
             patch("api.workspace_routes.engine.begin", return_value=tx):
            with self.assertRaises(Exception) as raised:
                await workspace_decide_plan_approval(
                    approval_id=7,
                    req=ApprovalRequest(approved=False),
                    project_id="project-a",
                    user={"id": "user-admin"},
                )
        self.assertEqual(getattr(raised.exception, "status_code", None), 404)


if __name__ == "__main__":
    unittest.main()
