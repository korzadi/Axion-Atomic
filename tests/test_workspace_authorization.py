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


if __name__ == "__main__":
    unittest.main()
