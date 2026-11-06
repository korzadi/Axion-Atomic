"""Pruebas HTTP de permisos por rol para las rutas principales de workspace."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import HTTPException

from api.main import app
from api.workspace_routes import _csrf_user


def enforce_role(user, project_id, allowed):
    if user["role"] not in allowed:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return user["role"]


class WorkspaceRoleHttpTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[_csrf_user] = lambda: {
            "id": "user-test", "email": "user@example.test",
            "display_name": "Test", "role": self.role,
        }
        self.role = "viewer"

    def tearDown(self):
        app.dependency_overrides.clear()

    def _post(self, path, json):
        return self.client.post(path, json=json)

    def test_viewer_can_chat_but_cannot_ingest_or_create_tasks(self):
        self.role = "viewer"
        with patch("api.workspace_routes._project_role", side_effect=enforce_role), \
             patch("api.workspace_routes.retrieve", return_value=""), \
             patch("api.workspace_routes.chat", return_value="respuesta") as chat:
            response = self._post("/workspace/chat/completions", {
                "project_id": "project-a",
                "messages": [{"role": "user", "content": "hola"}],
            })
            self.assertEqual(response.status_code, 200)
            chat.assert_called_once()

            denied_ingest = self._post("/workspace/knowledge/ingest", {
                "project_id": "project-a", "text": "contenido seguro", "source": "manual",
            })
            self.assertEqual(denied_ingest.status_code, 404)

            denied_task = self._post("/workspace/agent/tasks", {
                "project_id": "project-a", "goal": "Crear una prueba segura",
            })
            self.assertEqual(denied_task.status_code, 404)

    def test_editor_can_ingest_and_create_plan_but_not_decide_approvals(self):
        self.role = "editor"
        with patch("api.workspace_routes._project_role", side_effect=enforce_role), \
             patch("api.workspace_routes.ingest_text", return_value=1) as ingest, \
             patch("api.workspace_routes.create_plan", return_value={"steps": []}) as planner, \
             patch("api.workspace_routes.create_approval", return_value=7):
            response = self._post("/workspace/knowledge/ingest", {
                "project_id": "project-a", "text": "contenido seguro", "source": "manual",
            })
            self.assertEqual(response.status_code, 200)
            ingest.assert_called_once()

            task = self._post("/workspace/agent/tasks", {
                "project_id": "project-a", "goal": "Crear una prueba segura",
            })
            self.assertEqual(task.status_code, 200)
            planner.assert_called_once()

            # La ruta de decisión exige owner/admin; editor debe recibir 404 antes de DB.
            decision = self._post(
                "/workspace/agent/plan-approvals/7?project_id=project-a",
                {"approved": True, "note": "revisión"},
            )
            self.assertEqual(decision.status_code, 404)

    def test_owner_and_admin_can_decide_plan_approval_without_execution(self):
        for role in ("owner", "admin"):
            with self.subTest(role=role):
                self.role = role
                conn = unittest.mock.MagicMock()
                conn.execute.return_value.first.return_value = {"id": 7}
                transaction = unittest.mock.MagicMock()
                transaction.__enter__.return_value = conn
                with patch("api.workspace_routes._project_role", side_effect=enforce_role), \\
                     patch("api.workspace_routes.engine.begin", return_value=transaction):
                    response = self._post(
                        "/workspace/agent/plan-approvals/7?project_id=project-a",
                        {"approved": True, "note": "revisión humana"},
                    )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "approved")
                self.assertEqual(response.json()["execution"], "not_executed")

    def test_run_from_another_project_is_not_disclosed_over_http(self):
        from api.workspace_routes import _enabled_user

        app.dependency_overrides[_enabled_user] = lambda: {
            "id": "user-test", "email": "user@example.test", "role": "viewer",
        }
        conn = unittest.mock.MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = None
        db_context = unittest.mock.MagicMock()
        db_context.__enter__.return_value = conn
        with patch("api.workspace_routes._project_role", side_effect=enforce_role), \\
             patch("api.workspace_routes.engine.connect", return_value=db_context):
            response = self.client.get(
                "/workspace/agent/runs/run-owned-by-project-a?project_id=project-b"
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            conn.execute.call_args.args[1],
            {"run_id": "run-owned-by-project-a", "project_id": "project-b"},
        )


if __name__ == "__main__":
    unittest.main()
