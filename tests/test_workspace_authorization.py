import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from api.auth import authorize_project
from api.workspace_routes import _project_role, _enabled_user


class WorkspaceAuthorizationTests(unittest.TestCase):
    def _authorize_with_role(self, role, allowed_roles):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        result = MagicMock()
        result.scalar_one_or_none.return_value = role
        connection.execute.return_value = result

        with patch("api.auth.engine.connect", return_value=connection):
            resolved = authorize_project("user-123", "project-456", allowed_roles)

        params = connection.execute.call_args.args[1]
        self.assertEqual(params, {"user_id": "user-123", "project_id": "project-456"})
        return resolved

    def test_owner_admin_editor_and_viewer_can_read_project(self):
        read_roles = ("owner", "admin", "editor", "viewer")
        for role in read_roles:
            with self.subTest(role=role):
                self.assertEqual(self._authorize_with_role(role, read_roles), role)

    def test_viewer_cannot_perform_editor_operation(self):
        with self.assertRaises(HTTPException) as raised:
            self._authorize_with_role("viewer", ("owner", "admin", "editor"))
        self.assertEqual(raised.exception.status_code, 404)

    def test_editor_cannot_decide_approval(self):
        with self.assertRaises(HTTPException) as raised:
            self._authorize_with_role("editor", ("owner", "admin"))
        self.assertEqual(raised.exception.status_code, 404)

    def test_non_member_and_unknown_project_are_indistinguishable(self):
        with self.assertRaises(HTTPException) as raised:
            self._authorize_with_role(None, ("owner", "admin", "editor", "viewer"))
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Proyecto no encontrado")

    def test_workspace_checks_global_gate_before_session(self):
        with patch("api.workspace_routes.settings.auth_enabled", False), patch("api.workspace_routes.current_user") as current:
            with self.assertRaises(HTTPException) as raised:
                _enabled_user()
        self.assertEqual(raised.exception.status_code, 503)
        current.assert_not_called()

    def test_project_authorization_uses_authenticated_user_id(self):
        with patch("api.workspace_routes.authorize_project", return_value="editor") as authorize:
            role = _project_role(
                {"id": "user-123"},
                "project-456",
                ("owner", "admin", "editor"),
            )
        self.assertEqual(role, "editor")
        authorize.assert_called_once_with(
            "user-123", "project-456", ("owner", "admin", "editor")
        )


class WorkspaceAuthorizationHttpTests(unittest.TestCase):
    def _request_as_role(self, role, method, endpoint, payload=None):
        import asyncio
        import httpx
        from api.main import app
        from api.workspace_routes import _enabled_user, _csrf_user

        def resolve_role(user_id, project_id, allowed_roles):
            if role not in allowed_roles:
                raise HTTPException(status_code=404, detail="Proyecto no encontrado")
            return role

        async def request():
            overrides = app.dependency_overrides
            previous_enabled = overrides.get(_enabled_user)
            previous_csrf = overrides.get(_csrf_user)
            overrides[_enabled_user] = lambda: {"id": "user-123"}
            overrides[_csrf_user] = lambda: {"id": "user-123"}
            try:
                with patch("api.workspace_routes.authorize_project", side_effect=resolve_role), \\
                     patch("api.workspace_routes._enforce_workspace_limit"), \\
                     patch("api.workspace_routes._list_runs", return_value=[]), \\
                     patch("api.workspace_routes._get_run", return_value=None) as get_run, \\
                     patch("api.workspace_routes._decide_action_approval") as decide:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.request(method, endpoint, json=payload)
                    return response, get_run, decide
            finally:
                if previous_enabled is None:
                    overrides.pop(_enabled_user, None)
                else:
                    overrides[_enabled_user] = previous_enabled
                if previous_csrf is None:
                    overrides.pop(_csrf_user, None)
                else:
                    overrides[_csrf_user] = previous_csrf

        return asyncio.run(request())

    def test_viewer_can_read_runs_over_http(self):
        response, _, _ = self._request_as_role(
            "viewer", "GET", "/workspace/agent/runs?project_id=project-456"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})

    def test_viewer_cannot_read_approval_queue_over_http(self):
        response, _, _ = self._request_as_role(
            "viewer", "GET", "/workspace/agent/approvals?project_id=project-456"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Proyecto no encontrado")

    def test_non_member_receives_same_not_found_over_http(self):
        response, _, _ = self._request_as_role(
            None, "GET", "/workspace/agent/runs?project_id=project-456"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Proyecto no encontrado")

    def test_viewer_cannot_start_agent_run_over_http(self):
        response, _, _ = self._request_as_role(
            "viewer",
            "POST",
            "/workspace/agent/runs",
            {"project_id": "project-456", "goal": "crear un informe"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Proyecto no encontrado")

    def test_viewer_cannot_decide_agent_approval_over_http(self):
        response, _, decide = self._request_as_role(
            "viewer",
            "POST",
            "/workspace/agent/approvals/approval-123?project_id=project-456",
            {"approved": True, "note": "revisión"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Proyecto no encontrado")
        decide.assert_not_called()

    def test_run_detail_is_scoped_to_requested_project_over_http(self):
        response, get_run, _ = self._request_as_role(
            "viewer",
            "GET",
            "/workspace/agent/runs/run-789?project_id=project-456",
        )
        self.assertEqual(response.status_code, 404)
        get_run.assert_called_once_with("run-789", "project-456")


if __name__ == "__main__":
    unittest.main()
