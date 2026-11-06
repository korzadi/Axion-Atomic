import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.agent_workspace import build_authorized_project_toolset


class AuthorizedProjectToolsetTests(unittest.TestCase):
    def test_denied_membership_prevents_workspace_resolution(self):
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with patch("api.agent_workspace.authorize_project", side_effect=denied) as authorize:
            with patch("api.agent_workspace.build_project_toolset") as build:
                with self.assertRaises(HTTPException):
                    build_authorized_project_toolset({"id": "user-a"}, "project-x")
        authorize.assert_called_once_with("user-a", "project-x", ("owner", "admin", "editor"))
        build.assert_not_called()

    def test_missing_identity_prevents_authorization_and_resolution(self):
        with patch("api.agent_workspace.authorize_project") as authorize:
            with patch("api.agent_workspace.build_project_toolset") as build:
                with self.assertRaises(ValueError):
                    build_authorized_project_toolset({}, "project-x")
        authorize.assert_not_called()
        build.assert_not_called()

    def test_authorized_user_passes_only_project_identifier_to_factory(self):
        expected = (object(), {"read_file": object()})
        with patch("api.agent_workspace.authorize_project", return_value="editor") as authorize:
            with patch("api.agent_workspace.build_project_toolset", return_value=expected) as build:
                result = build_authorized_project_toolset(
                    {"id": "user-a"}, "project-x", workspace_root="/tmp/workspaces"
                )
        authorize.assert_called_once_with("user-a", "project-x", ("owner", "admin", "editor"))
        build.assert_called_once()
        self.assertEqual(build.call_args.args, ("/tmp/workspaces", "project-x"))
        self.assertIs(result, expected)


if __name__ == "__main__":
    unittest.main()
