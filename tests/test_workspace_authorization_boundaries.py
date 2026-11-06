import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.schemas import ApprovalRequest, ChatRequest, IngestRequest, Message, TaskRequest
from api.workspace_routes import (
    workspace_approve,
    workspace_chat,
    workspace_ingest,
    workspace_list_knowledge_sources,
    workspace_delete_knowledge_source,
    workspace_task,
)


class WorkspaceAuthorizationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        admission = patch("api.workspace_routes._enforce_workspace_limit")
        admission.start()
        self.addCleanup(admission.stop)

    async def test_chat_rejects_non_member_before_retrieval_or_model_call(self):
        request = ChatRequest(
            project_id="foreign-project",
            messages=[Message(role="user", content="Lee los archivos")],
        )
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.retrieve", new=AsyncMock()) as retrieve,
            patch("api.workspace_routes.chat_with_usage", new=AsyncMock()) as chat,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_chat(request, user={"id": "user-a"})
        self.assertEqual(raised.exception.status_code, 404)
        retrieve.assert_not_awaited()
        chat.assert_not_awaited()

    async def test_task_rejects_non_editor_before_planning_or_persisting(self):
        request = TaskRequest(project_id="foreign-project", goal="Analizar el proyecto")
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.create_plan", new=AsyncMock()) as create_plan,
            patch("api.workspace_routes.create_approval") as create_approval,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_task(request, user={"id": "user-a"})
        self.assertEqual(raised.exception.status_code, 404)
        create_plan.assert_not_awaited()
        create_approval.assert_not_called()

    async def test_approval_rejects_non_owner_before_database_write(self):
        request = ApprovalRequest(approved=True, note="Aprobado")
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.engine") as engine,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_approve(
                    "approval-1", request, project_id="foreign-project",
                    user={"id": "user-a"},
                )
        self.assertEqual(raised.exception.status_code, 404)
        engine.begin.assert_not_called()


    async def test_approval_updates_gate_and_run_action_in_one_transaction(self):
        from contextlib import contextmanager

        class Result:
            rowcount = 1
            def first(self):
                return type("ApprovalRow", (), {"action_hash": "hash-1"})()

        class Connection:
            def __init__(self):
                self.calls = []
            def execute(self, statement, params):
                self.calls.append((str(statement), params))
                return Result()

        class Engine:
            def __init__(self):
                self.connection = Connection()
                self.transactions = 0
            @contextmanager
            def begin(self):
                self.transactions += 1
                yield self.connection

        engine = Engine()
        request = ApprovalRequest(approved=True, note="Revisado")
        with patch("api.workspace_routes._project_role", return_value="owner"), \
             patch("api.workspace_routes.engine", engine):
            result = await workspace_approve(
                "approval-1", request, project_id="project-1",
                user={"id": "owner-1"},
            )

        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["execution"], "not_executed")
        self.assertEqual(engine.transactions, 1)
        self.assertEqual(len(engine.connection.calls), 2)
        approval_sql, approval_params = engine.connection.calls[0]
        action_sql, action_params = engine.connection.calls[1]
        self.assertIn("UPDATE action_approvals", approval_sql)
        self.assertIn("expires_at > now()", approval_sql)
        self.assertIn("UPDATE agent_run_actions", action_sql)
        self.assertEqual(approval_params["approval_id"], "approval-1")
        self.assertEqual(action_params["proposal_id"], "approval-1")
        self.assertEqual(action_params["action_hash"], "hash-1")
        self.assertEqual(action_params["state"], "approved")

    async def test_approval_returns_conflict_when_run_action_does_not_match(self):
        from contextlib import contextmanager

        class Result:
            def __init__(self, rowcount=0):
                self.rowcount = rowcount
            def first(self):
                return type("ApprovalRow", (), {"action_hash": "hash-1"})()

        class Connection:
            def __init__(self):
                self.calls = []
            def execute(self, statement, params):
                self.calls.append((str(statement), params))
                return Result(rowcount=0) if len(self.calls) == 2 else Result(rowcount=1)

        class Engine:
            @contextmanager
            def begin(self):
                yield connection

        connection = Connection()
        request = ApprovalRequest(approved=True, note="Revisado")
        with patch("api.workspace_routes._project_role", return_value="owner"), \
             patch("api.workspace_routes.engine", Engine()):
            with self.assertRaises(HTTPException) as raised:
                await workspace_approve(
                    "approval-1", request, project_id="project-1",
                    user={"id": "owner-1"},
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(len(connection.calls), 2)



    async def test_agent_task_rate_limit_blocks_planning(self):
        denied = HTTPException(status_code=429, detail="rate limited")
        request = TaskRequest(project_id="project-1", goal="Planificar tarea segura")
        with (
            patch("api.workspace_routes._project_role", return_value="editor"),
            patch("api.workspace_routes._enforce_workspace_limit", side_effect=denied) as limit,
            patch("api.workspace_routes.create_plan", new=AsyncMock()) as planner,
            patch("api.workspace_routes.create_approval") as approval,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_task(request, user={"id": "user-1"})
        self.assertEqual(raised.exception.status_code, 429)
        limit.assert_called_once()
        self.assertEqual(limit.call_args.args, ("user-1", "project-1", "agent"))
        self.assertEqual(limit.call_args.kwargs["user_limit"], 10)
        self.assertEqual(limit.call_args.kwargs["project_limit"], 30)
        planner.assert_not_awaited()
        approval.assert_not_called()

    async def test_agent_run_rate_limit_blocks_runtime_start(self):
        from api.workspace_routes import workspace_agent_start
        denied = HTTPException(status_code=429, detail="rate limited")
        request = TaskRequest(project_id="project-1", goal="Ejecutar tarea segura")
        with (
            patch("api.workspace_routes._enforce_workspace_limit", side_effect=denied) as limit,
            patch("api.workspace_routes._agent_runtime") as runtime,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_agent_start(request, user={"id": "user-1"})
        self.assertEqual(raised.exception.status_code, 429)
        limit.assert_called_once()
        runtime.assert_not_called()

    async def test_agent_resume_rate_limit_blocks_runtime_resume(self):
        from api.workspace_routes import workspace_agent_resume
        denied = HTTPException(status_code=429, detail="rate limited")
        with (
            patch("api.workspace_routes._enforce_workspace_limit", side_effect=denied) as limit,
            patch("api.workspace_routes._agent_runtime") as runtime,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_agent_resume(
                    "run-1", project_id="project-1", user={"id": "user-1"}
                )
        self.assertEqual(raised.exception.status_code, 429)
        limit.assert_called_once()
        self.assertEqual(limit.call_args.args, ("user-1", "project-1", "agent"))
        runtime.assert_not_called()


    async def test_knowledge_ingest_maps_embedding_outage_to_safe_503(self):
        from rag.service import EmbeddingServiceUnavailable
        request = IngestRequest(project_id="project-1", text="documentación segura")
        with (
            patch("api.workspace_routes._project_role", return_value="editor"),
            patch("api.workspace_routes.ingest_text", new=AsyncMock(side_effect=EmbeddingServiceUnavailable("El servicio de embeddings no está disponible"))),
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_ingest(request, user={"id": "user-1"})
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "El servicio de embeddings no está disponible")

    async def test_knowledge_ingest_maps_vector_store_outage_to_safe_503(self):
        from rag.service import KnowledgeStoreUnavailable
        request = IngestRequest(project_id="project-1", text="documentación segura")
        with (
            patch("api.workspace_routes._project_role", return_value="editor"),
            patch("api.workspace_routes.ingest_text", new=AsyncMock(side_effect=KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible"))),
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_ingest(request, user={"id": "user-1"})
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "El almacén de conocimiento no está disponible")

    async def test_knowledge_ingest_rejects_non_editor_before_embedding(self):
        request = IngestRequest(project_id="project-1", text="documentación segura")
        denied = HTTPException(status_code=403, detail="forbidden")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.ingest_text", new=AsyncMock()) as ingest,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_ingest(request, user={"id": "user-1"})
        self.assertEqual(raised.exception.status_code, 403)
        ingest.assert_not_awaited()


    async def test_knowledge_source_delete_requires_editor_role(self):
        denied = HTTPException(status_code=403, detail="forbidden")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.delete_source", new=AsyncMock()) as delete,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_delete_knowledge_source(
                    "12345678-1234-5678-1234-567812345678",
                    project_id="project-1", user={"id": "user-1"},
                )
        self.assertEqual(raised.exception.status_code, 403)
        delete.assert_not_awaited()

    async def test_knowledge_source_delete_maps_store_outage_to_503(self):
        from rag.service import KnowledgeStoreUnavailable
        source_id = "12345678-1234-5678-1234-567812345678"
        with (
            patch("api.workspace_routes._project_role", return_value="editor"),
            patch("api.workspace_routes.delete_source", new=AsyncMock(side_effect=KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible"))) as delete,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_delete_knowledge_source(source_id, project_id="project-1", user={"id": "user-1"})
        self.assertEqual(raised.exception.status_code, 503)
        delete.assert_awaited_once_with(source_id, "project-1")


    async def test_knowledge_source_list_requires_project_membership(self):
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes.list_sources", new=AsyncMock()) as listing,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_list_knowledge_sources(project_id="foreign-project", limit=100, user={"id": "user-a"})
        self.assertEqual(raised.exception.status_code, 404)
        listing.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
