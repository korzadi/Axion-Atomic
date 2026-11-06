import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.auth_routes import create_project
from api.schemas import ProjectCreateRequest


class ProjectCreationRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_route_uses_coordinated_project_service(self):
        expected = {"id": "project-id", "name": "Alpha", "role": "owner"}
        with patch("api.auth_routes.create_owned_project_with_workspace", return_value=expected) as create:
            result = await create_project(
                ProjectCreateRequest(name="Alpha"), user={"id": "user-1"}
            )
        create.assert_called_once_with("user-1", "Alpha")
        self.assertEqual(result, {"project": expected})

    async def test_workspace_provisioning_error_returns_service_unavailable(self):
        with patch(
            "api.auth_routes.create_owned_project_with_workspace",
            side_effect=FileNotFoundError("workspace root missing"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await create_project(
                    ProjectCreateRequest(name="Alpha"), user={"id": "user-1"}
                )
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("workspace root", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
