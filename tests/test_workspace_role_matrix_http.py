"""Pruebas HTTP de permisos por rol para las rutas principales de workspace."""
import unittest
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.ollama import InferenceResult
from api.workspace_routes import _csrf_user


def enforce_role(user, project_id, allowed):
    if user["role"] not in allowed:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return user["role"]


class WorkspaceRoleHttpTests(unittest.TestCase):
    def setUp(self):
        self.role = "viewer"
        self.admission_patch = patch("api.workspace_routes._enforce_workspace_limit")
        self.admission_patch.start()
        self.client = TestClient(app)
        app.dependency_overrides[_csrf_user] = lambda: {
            "id": "user-test",
            "email": "user@example.test",
            "display_name": "Test",
            "role": self.role,
        }

    def tearDown(self):
        app.dependency_overrides.clear()
        self.admission_patch.stop()

    def _post(self, path, payload):
        return self.client.post(path, json=payload)

    def test_editor_can_chat_and_cannot_decide_approval(self):
        self.role = "editor"
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.settings.chat_model", "atomic-code"),
            patch("api.workspace_routes.retrieve", return_value=""),
            patch("api.workspace_routes.persist_shadow_usage_event") as persist_usage,
            patch("api.workspace_routes._save_chat_history"),
            patch("api.workspace_routes.chat_with_usage", new_callable=AsyncMock, return_value=InferenceResult(
                content="respuesta", requested_model="atomic-code", returned_model="atomic-code",
                done=True, prompt_eval_count=3, eval_count=2, total_duration_ns=10,
                load_duration_ns=None, prompt_eval_duration_ns=None, eval_duration_ns=None,
                usage_source="ollama_response",
            )) as chat,
        ):
            with self.assertLogs("axion.usage.shadow", level="INFO") as usage_logs:
                response = self._post("/workspace/chat/completions", {
                    "project_id": "project-a",
                    "messages": [{"role": "user", "content": "hola"}],
                })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["choices"][0]["message"]["content"], "respuesta")
            chat.assert_awaited_once()
            persist_usage.assert_called_once()
            self.assertEqual(persist_usage.call_args.kwargs["user_id"], "user-test")
            self.assertEqual(persist_usage.call_args.kwargs["project_id"], "project-a")
            self.assertIn('"event":"inference_usage_shadow"', usage_logs.output[0])
            event = json.loads(usage_logs.output[0].split("INFO:axion.usage.shadow:", 1)[-1])
            self.assertEqual(event["user_id"], "user-test")
            self.assertEqual(event["project_id"], "project-a")
            self.assertTrue(uuid.UUID(event["request_id"]))
            self.assertEqual(response.json()["id"], f"chatcmpl-{event['request_id']}")
            self.assertNotIn("hola", usage_logs.output[0])

            self.role = "viewer"
            denied_ingest = self._post("/workspace/knowledge/ingest", {
                "project_id": "project-a",
                "text": "contenido seguro",
                "source": "manual",
            })
            self.assertEqual(denied_ingest.status_code, 404)

            denied_task = self._post("/workspace/agent/tasks", {
                "project_id": "project-a",
                "goal": "Crear una prueba segura",
            })
            self.assertEqual(denied_task.status_code, 404)

    def test_viewer_cannot_chat_or_trigger_rag_or_inference(self):
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.retrieve", return_value="") as retrieve,
            patch("api.workspace_routes.chat_with_usage", new_callable=AsyncMock) as chat,
        ):
            response = self._post("/workspace/chat/completions", {
                "project_id": "project-a",
                "messages": [{"role": "user", "content": "hola"}],
            })
        self.assertEqual(response.status_code, 404)
        retrieve.assert_not_awaited()
        chat.assert_not_awaited()

    def test_chat_succeeds_even_if_shadow_logging_and_warning_fail(self):
        self.role = "editor"
        result = InferenceResult(
            content="respuesta segura", requested_model="atomic-code",
            returned_model="atomic-code", done=True, prompt_eval_count=3,
            eval_count=2, total_duration_ns=10, load_duration_ns=None,
            prompt_eval_duration_ns=None, eval_duration_ns=None,
            usage_source="ollama_response",
        )
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.settings.chat_model", "atomic-code"),
            patch("api.workspace_routes.retrieve", return_value=""),
            patch("api.workspace_routes.chat_with_usage", new_callable=AsyncMock, return_value=result),
            patch("api.workspace_routes.persist_shadow_usage_event", side_effect=RuntimeError("db unavailable")),
            patch("api.workspace_routes._save_chat_history"),
            patch("api.workspace_routes.logger.info", side_effect=RuntimeError("logger unavailable")),
            patch("api.workspace_routes.logger.warning", side_effect=RuntimeError("logger unavailable")),
        ):
            response = self._post("/workspace/chat/completions", {
                "project_id": "project-a",
                "messages": [{"role": "user", "content": "consulta"}],
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["choices"][0]["message"]["content"], "respuesta segura")

    def test_rejected_model_identity_is_not_persisted_as_usage(self):
        self.role = "editor"
        result = InferenceResult(
            content="respuesta de modelo inesperado", requested_model="atomic-code",
            returned_model="unexpected-model", done=True, prompt_eval_count=3,
            eval_count=2, total_duration_ns=10, load_duration_ns=None,
            prompt_eval_duration_ns=None, eval_duration_ns=None,
            usage_source="ollama_response",
        )
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.settings.chat_model", "atomic-code"),
            patch("api.workspace_routes.retrieve", return_value=""),
            patch("api.workspace_routes.chat_with_usage", new_callable=AsyncMock, return_value=result),
            patch("api.workspace_routes.persist_shadow_usage_event") as persist_usage,
            patch("api.workspace_routes._save_chat_history") as save_history,
        ):
            response = self._post("/workspace/chat/completions", {
                "project_id": "project-a",
                "messages": [{"role": "user", "content": "hola"}],
            })
        self.assertEqual(response.status_code, 503)
        persist_usage.assert_not_called()
        save_history.assert_not_called()

    def test_incomplete_inference_is_not_persisted_as_usage(self):
        self.role = "editor"
        result = InferenceResult(
            content="respuesta parcial", requested_model="atomic-code",
            returned_model="atomic-code", done=False, prompt_eval_count=3,
            eval_count=2, total_duration_ns=10, load_duration_ns=None,
            prompt_eval_duration_ns=None, eval_duration_ns=None,
            usage_source="ollama_response",
        )
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.settings.chat_model", "atomic-code"),
            patch("api.workspace_routes.retrieve", return_value=""),
            patch("api.workspace_routes.chat_with_usage", new_callable=AsyncMock, return_value=result),
            patch("api.workspace_routes.persist_shadow_usage_event") as persist_usage,
            patch("api.workspace_routes._save_chat_history") as save_history,
        ):
            response = self._post("/workspace/chat/completions", {
                "project_id": "project-a",
                "messages": [{"role": "user", "content": "hola"}],
            })
        self.assertEqual(response.status_code, 503)
        persist_usage.assert_not_called()
        save_history.assert_not_called()

    def test_editor_can_ingest_and_create_plan_but_not_decide_approvals(self):
        self.role = "editor"
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.ingest_text", return_value=1) as ingest,
            patch("api.workspace_routes.create_plan", return_value={"steps": []}) as planner,
            patch("api.workspace_routes.create_approval", return_value=7),
        ):
            response = self._post("/workspace/knowledge/ingest", {
                "project_id": "project-a",
                "text": "contenido seguro",
                "source": "manual",
            })
            self.assertEqual(response.status_code, 200)
            ingest.assert_called_once()

            task = self._post("/workspace/agent/tasks", {
                "project_id": "project-a",
                "goal": "Crear una prueba segura",
            })
            self.assertEqual(task.status_code, 200)
            planner.assert_called_once()

            decision = self._post(
                "/workspace/agent/plan-approvals/7?project_id=project-a",
                {"approved": True, "note": "revisión"},
            )
            self.assertEqual(decision.status_code, 404)

    def test_owner_and_admin_can_decide_plan_approval_without_execution(self):
        for role in ("owner", "admin"):
            with self.subTest(role=role):
                self.role = role
                conn = MagicMock()
                conn.execute.return_value.first.return_value = {"id": 7}
                transaction = MagicMock()
                transaction.__enter__.return_value = conn
                with (
                    patch("api.workspace_routes._project_role", side_effect=enforce_role),
                    patch("api.workspace_routes.engine.begin", return_value=transaction),
                ):
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
            "id": "user-test",
            "email": "user@example.test",
            "role": "viewer",
        }
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = None
        db_context = MagicMock()
        db_context.__enter__.return_value = conn
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.engine.connect", return_value=db_context),
        ):
            response = self.client.get(
                "/workspace/agent/runs/run-owned-by-project-a?project_id=project-b"
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            conn.execute.call_args.args[1],
            {"run_id": "run-owned-by-project-a", "project_id": "project-b"},
        )


    def test_editor_cannot_decide_action_approval_before_database_access(self):
        self.role = "editor"
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.engine.begin") as begin,
        ):
            response = self._post(
                "/workspace/agent/approvals/action-7?project_id=project-a",
                {"approved": True, "note": "no autorizado"},
            )
        self.assertEqual(response.status_code, 404)
        begin.assert_not_called()

    def test_owner_and_admin_can_decide_action_approval_without_execution(self):
        from types import SimpleNamespace

        for role in ("owner", "admin"):
            with self.subTest(role=role):
                self.role = role
                conn = MagicMock()
                conn.execute.side_effect = [
                    MagicMock(first=MagicMock(return_value=SimpleNamespace(
                        id="action-7", action_hash="hash-test"
                    ))),
                    MagicMock(rowcount=1),
                ]
                transaction = MagicMock()
                transaction.__enter__.return_value = conn
                with (
                    patch("api.workspace_routes._project_role", side_effect=enforce_role),
                    patch("api.workspace_routes.engine.begin", return_value=transaction),
                ):
                    response = self._post(
                        "/workspace/agent/approvals/action-7?project_id=project-a",
                        {"approved": True, "note": "revisión humana"},
                    )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "approved")
                self.assertEqual(response.json()["execution"], "not_executed")
                self.assertEqual(conn.execute.call_count, 2)
                self.assertEqual(
                    conn.execute.call_args_list[1].args[1],
                    {
                        "state": "approved",
                        "project_id": "project-a",
                        "proposal_id": "action-7",
                        "action_hash": "hash-test",
                    },
                )

    def test_action_approval_rolls_back_when_action_link_is_missing(self):
        from types import SimpleNamespace

        self.role = "owner"
        conn = MagicMock()
        conn.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=SimpleNamespace(
                id="action-7", action_hash="hash-test"
            ))),
            MagicMock(rowcount=0),
        ]
        transaction = MagicMock()
        transaction.__enter__.return_value = conn
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.engine.begin", return_value=transaction),
        ):
            response = self._post(
                "/workspace/agent/approvals/action-7?project_id=project-a",
                {"approved": True, "note": "revisión humana"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(transaction.__exit__.called)
        self.assertIsNotNone(transaction.__exit__.call_args.args[0])

    def test_action_approval_rejects_another_projects_record(self):
        self.role = "admin"
        conn = MagicMock()
        conn.execute.return_value.first.return_value = None
        transaction = MagicMock()
        transaction.__enter__.return_value = conn
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.engine.begin", return_value=transaction),
        ):
            response = self._post(
                "/workspace/agent/approvals/action-owned-by-a?project_id=project-b",
                {"approved": True, "note": "revisión humana"},
            )
        self.assertEqual(response.status_code, 404)
        conn.execute.assert_called_once()


    def test_run_list_is_scoped_to_requested_project(self):
        from api.workspace_routes import _enabled_user

        app.dependency_overrides[_enabled_user] = lambda: {
            "id": "user-test", "email": "user@example.test", "role": "viewer",
        }
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.all.return_value = [
            {"id": "run-project-a", "goal": "test", "status": "completed"}
        ]
        db_context = MagicMock()
        db_context.__enter__.return_value = conn
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.engine.connect", return_value=db_context),
        ):
            response = self.client.get("/workspace/agent/runs?project_id=project-a")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], "run-project-a")
        sql = str(conn.execute.call_args.args[0])
        self.assertIn("WHERE project_id=:project_id", sql)
        self.assertEqual(conn.execute.call_args.args[1], {"project_id": "project-a", "limit": 20})

    def test_chat_retrieval_receives_authorized_project_id(self):
        self.role = "editor"
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.settings.chat_model", "atomic-code"),
            patch("api.workspace_routes.retrieve", return_value="") as retrieve_mock,
            patch("api.workspace_routes._save_chat_history"),
            patch("api.workspace_routes.chat_with_usage", new_callable=AsyncMock, return_value=InferenceResult(
                content="respuesta", requested_model="atomic-code", returned_model="atomic-code",
                done=True, prompt_eval_count=3, eval_count=2, total_duration_ns=10,
                load_duration_ns=None, prompt_eval_duration_ns=None, eval_duration_ns=None,
                usage_source="ollama_response",
            )),
        ):
            response = self._post("/workspace/chat/completions", {
                "project_id": "project-a",
                "messages": [{"role": "user", "content": "consulta privada"}],
            })
        self.assertEqual(response.status_code, 200)
        retrieve_mock.assert_awaited_once_with("consulta privada", project_id="project-a", limit=5)

    def test_authorize_project_checks_user_and_project_membership(self):
        from api.auth import authorize_project

        conn = MagicMock()
        conn.execute.return_value.scalar_one_or_none.return_value = "editor"
        db_context = MagicMock()
        db_context.__enter__.return_value = conn
        with patch("api.auth.engine.connect", return_value=db_context):
            role = authorize_project("user-a", "project-a", ("owner", "admin", "editor"))
        self.assertEqual(role, "editor")
        params = conn.execute.call_args.args[1]
        self.assertEqual(params, {"user_id": "user-a", "project_id": "project-a"})

    def test_authorize_project_hides_non_member_project(self):
        from api.auth import authorize_project

        conn = MagicMock()
        conn.execute.return_value.scalar_one_or_none.return_value = None
        db_context = MagicMock()
        db_context.__enter__.return_value = conn
        with patch("api.auth.engine.connect", return_value=db_context):
            with self.assertRaises(HTTPException) as caught:
                authorize_project("user-b", "project-a", ("owner", "admin", "editor", "viewer"))
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
