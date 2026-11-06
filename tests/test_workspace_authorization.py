import unittest
from unittest.mock import patch

from api.workspace_routes import _project_role


class WorkspaceAuthorizationTests(unittest.TestCase):
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
