import unittest
from unittest.mock import patch
from starlette.requests import Request

from fastapi import HTTPException

from api.auth_routes import create_project
from api.schemas import ProjectCreateRequest


def _request():
    return Request({
        "type": "http", "method": "POST", "path": "/auth/projects",
        "headers": [], "query_string": b"", "scheme": "https",
        "server": ("localhost", 443), "client": ("127.0.0.1", 12345),
    })


class ProjectCreationRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_route_rate_limits_each_user_before_provisioning(self):
        expected = {"id": "project-id", "name": "Alpha", "role": "owner"}
        with (
            patch("api.auth_routes._enforce_rate_limit") as limit,
            patch("api.auth_routes.create_owned_project_with_workspace", return_value=expected) as create,
        ):
            result = await create_project(
                ProjectCreateRequest(name="Alpha"), request=_request(), user={"id": "user-1"}
            )
        limit.assert_called_once()
        args, kwargs = limit.call_args
        self.assertEqual(args[0].url.path, "/auth/projects")
        self.assertEqual(kwargs["namespace"], "auth:projects:create:user")
        self.assertEqual(kwargs["subject"], "user-1")
        self.assertEqual(kwargs["limit"], 10)
        self.assertEqual(kwargs["window"].total_seconds(), 3600)
        create.assert_called_once_with("user-1", "Alpha")
        self.assertEqual(result, {"project": expected})

    async def test_rate_limit_rejection_prevents_workspace_provisioning(self):
        with (
            patch("api.auth_routes._enforce_rate_limit", side_effect=HTTPException(
                status_code=429, detail="Demasiadas solicitudes", headers={"Retry-After": "3600"}
            )),
            patch("api.auth_routes.create_owned_project_with_workspace") as create,
        ):
            with self.assertRaises(HTTPException) as raised:
                await create_project(
                    ProjectCreateRequest(name="Alpha"), request=_request(), user={"id": "user-1"}
                )
        self.assertEqual(raised.exception.status_code, 429)
        create.assert_not_called()

    async def test_workspace_provisioning_error_returns_service_unavailable(self):
        with (
            patch("api.auth_routes._enforce_rate_limit"),
            patch("api.auth_routes.create_owned_project_with_workspace", side_effect=FileNotFoundError("workspace root missing")),
        ):
            with self.assertRaises(HTTPException) as raised:
                await create_project(
                    ProjectCreateRequest(name="Alpha"), request=_request(), user={"id": "user-1"}
                )
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("workspace root", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
