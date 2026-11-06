import unittest
from unittest.mock import patch

from api.workspace_routes import _project_role, _enabled_user


class WorkspaceAuthorizationTests(unittest.TestCase):
    def test_workspace_checks_global_gate_before_session(self):
        with patch("api.workspace_routes.settings.auth_enabled", False), patch("api.workspace_routes.current_user") as current:
            from fastapi import HTTPException
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
