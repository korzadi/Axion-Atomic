"""Pruebas de integración RAG con el motor Qdrant local real (sin red)."""
import unittest
from unittest.mock import AsyncMock, patch

from qdrant_client import QdrantClient

from rag import service


class RagQdrantIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = QdrantClient(":memory:")
        self.collection = "rag_integration_test"
        self.client_ref = service.client
        self.collection_ref = service.settings.qdrant_collection
        self.checked_ref = service._collection_checked_at
        service.client = self.client
        service.settings.qdrant_collection = self.collection
        service._collection_checked_at = 0.0
        self.embedding = [1.0] + [0.0] * (service.settings.embed_dimension - 1)
        self.embed_patch = patch.object(service, "embed", new=AsyncMock(return_value=self.embedding))
        self.embed_patch.start()

    async def asyncTearDown(self):
        self.embed_patch.stop()
        service.client = self.client_ref
        service.settings.qdrant_collection = self.collection_ref
        service._collection_checked_at = self.checked_ref
        self.client.close()

    async def test_project_scoped_source_lifecycle_against_qdrant(self):
        source_id = "12345678-1234-5678-1234-567812345678"
        chunks = await service.ingest_text(
            "Documentación privada del proyecto alfa.", "manual-alfa", "project-alfa",
            source_id=source_id,
        )
        self.assertEqual(chunks, 1)

        listed = await service.list_sources("project-alfa")
        self.assertEqual(len(listed["sources"]), 1)
        self.assertEqual(listed["sources"][0]["source_id"], source_id)
        self.assertEqual(listed["sources"][0]["chunks"], 1)
        self.assertEqual((await service.list_sources("project-beta"))["sources"], [])

        context = await service.retrieve("documentación privada", "project-alfa")
        self.assertIn("Documentación privada", context)
        self.assertNotIn("Documentación privada", await service.retrieve("documentación privada", "project-beta"))

        replaced = await service.replace_source(
            source_id, "Contenido actualizado del proyecto alfa.", "manual-alfa-v2", "project-alfa"
        )
        self.assertEqual(replaced, 1)
        updated = await service.list_sources("project-alfa")
        self.assertEqual(updated["sources"][0]["source"], "manual-alfa-v2")
        self.assertEqual(updated["sources"][0]["chunks"], 1)

        await service.delete_source(source_id, "project-alfa")
        self.assertEqual((await service.list_sources("project-alfa"))["sources"], [])
        self.assertEqual((await service.list_sources("project-beta"))["sources"], [])


if __name__ == "__main__":
    unittest.main()
