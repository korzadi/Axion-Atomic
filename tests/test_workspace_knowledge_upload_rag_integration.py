"""Integración de extracción y ruta de carga con doble del protocolo Qdrant."""
import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile
from tests.fake_qdrant import FakeQdrantClient

from api.workspace_routes import workspace_upload_knowledge_document
from rag import service


class WorkspaceKnowledgeUploadRagIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = FakeQdrantClient()
        self.collection = "workspace_upload_rag_integration"
        self.previous_client = service.client
        self.previous_collection = service.settings.qdrant_collection
        self.previous_checked_at = service._collection_checked_at
        service.client = self.client
        service.settings.qdrant_collection = self.collection
        service._collection_checked_at = -service._COLLECTION_CHECK_INTERVAL_SECONDS

        vector = [1.0] + [0.0] * (service.settings.embed_dimension - 1)
        self.embedding_patch = patch.object(service, "embed", new=AsyncMock(return_value=vector))
        self.embedding_patch.start()

        async def run_on_test_thread(function, *args, **kwargs):
            # El doble de protocolo no requiere servidor ni almacenamiento local.
            return function(*args, **kwargs)

        self.thread_patch = patch.object(service.asyncio, "to_thread", new=run_on_test_thread)
        self.thread_patch.start()

    async def asyncTearDown(self):
        self.thread_patch.stop()
        self.embedding_patch.stop()
        service.client = self.previous_client
        service.settings.qdrant_collection = self.previous_collection
        service._collection_checked_at = self.previous_checked_at
        self.client.close()

    async def test_http_handler_extracts_indexes_lists_and_retrieves_uploaded_file(self):
        upload = UploadFile(
            filename="manual.txt",
            file=io.BytesIO("Guía privada de despliegue AXION para proyecto alfa.".encode("utf-8")),
        )
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
        ):
            result = await workspace_upload_knowledge_document(
                "project-alfa", upload, {"id": "integration-user"}
            )

        self.assertEqual(result["status"], "indexed")
        self.assertEqual(result["project_id"], "project-alfa")
        self.assertEqual(result["source"], "manual.txt")
        self.assertGreaterEqual(result["chunks"], 1)
        self.assertTrue(upload.file.closed)

        listed = await service.list_sources("project-alfa")
        self.assertEqual(len(listed["sources"]), 1)
        self.assertEqual(listed["sources"][0]["source_id"], result["source_id"])
        self.assertEqual(listed["sources"][0]["source"], "manual.txt")

        retrieved = await service.retrieve("guía privada de despliegue", "project-alfa")
        self.assertIn("Guía privada de despliegue AXION", retrieved)
        isolated = await service.retrieve("guía privada de despliegue", "project-beta")
        self.assertNotIn("Guía privada de despliegue AXION", isolated)


if __name__ == "__main__":
    unittest.main()
