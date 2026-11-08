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


    async def test_delete_source_removes_all_embedding_versions_only_in_own_project(self):
        source_id = "12345678-1234-5678-1234-567812345678"
        await service.ingest_text(
            "Contenido privado del proyecto A.", "a.txt", "project-a", source_id
        )
        await service.ingest_text(
            "Contenido privado del proyecto B.", "b.txt", "project-b", source_id
        )

        before = list(self.client.points.values())
        self.assertEqual(
            {point.payload["project_id"] for point in before},
            {"project-a", "project-b"},
        )
        self.assertTrue(all(point.payload["source_id"] == source_id for point in before))

        await service.delete_source(source_id, "project-a")

        remaining = list(self.client.points.values())
        self.assertTrue(remaining)
        self.assertTrue(all(point.payload["project_id"] == "project-b" for point in remaining))
        self.assertTrue(all(point.payload["source_id"] == source_id for point in remaining))
        self.assertTrue(all("proyecto B" in point.payload["text"] for point in remaining))


    async def test_retrieval_never_mixes_models_with_equal_dimensions(self):
        await service.ingest_text("Contenido del modelo A.", "a.txt", "project-models")
        model_a = service.settings.embed_model
        service.settings.embed_model = model_a + "-alternate"
        try:
            await service.ingest_text("Contenido del modelo B.", "b.txt", "project-models")
            retrieved_b = await service.retrieve("consulta", "project-models")
            self.assertIn("Contenido del modelo B.", retrieved_b)
            self.assertNotIn("Contenido del modelo A.", retrieved_b)
            model_b_points = [
                point for point in self.client.points.values()
                if point.payload.get("project_id") == "project-models"
                and point.payload.get("text") == "Contenido del modelo B."
            ]
            self.assertEqual(len(model_b_points), 1)
            self.assertEqual(
                model_b_points[0].payload["embedding_model"],
                service.EmbeddingIdentity.from_settings(service.settings).model,
            )
        finally:
            service.settings.embed_model = model_a

    async def test_legacy_points_block_retrieval_instead_of_being_silently_hidden(self):
        from qdrant_client import models
        service.ensure_collection()
        self.client.upsert(
            collection_name=self.collection,
            points=[models.PointStruct(
                id="legacy-point",
                vector=[1.0] + [0.0] * (service.settings.embed_dimension - 1),
                payload={"project_id": "project-legacy", "path": "legacy.txt", "text": "old context"},
            )],
        )
        with self.assertRaises(service.EmbeddingIdentityMigrationRequired):
            await service.retrieve("consulta", "project-legacy")

    async def test_malformed_embedding_identity_blocks_retrieval(self):
        from qdrant_client import models
        service.ensure_collection()
        malformed_payloads = [
            {"embedding_model": "   ", "embedding_dimension": service.settings.embed_dimension},
            {"embedding_model": "nomic-embed-text:latest", "embedding_dimension": True},
            {"embedding_model": "nomic-embed-text:latest", "embedding_dimension": 0},
            {"embedding_model": "nomic-embed-text:latest", "embedding_dimension": "768"},
        ]
        for index, identity in enumerate(malformed_payloads):
            project_id = f"project-malformed-{index}"
            self.client.upsert(
                collection_name=self.collection,
                points=[models.PointStruct(
                    id=f"malformed-point-{index}",
                    vector=[1.0] + [0.0] * (service.settings.embed_dimension - 1),
                    payload={
                        "project_id": project_id,
                        "path": "malformed.txt",
                        "text": "must not be retrieved",
                        **identity,
                    },
                )],
            )
            with self.subTest(identity=identity):
                with self.assertRaises(service.EmbeddingIdentityMigrationRequired):
                    await service.retrieve("consulta", project_id)


if __name__ == "__main__":
    unittest.main()
