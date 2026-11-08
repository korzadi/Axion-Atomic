"""Rollback de replace_source con fallo inyectado — unitario, sin servidor Qdrant.

Inyecta un fallo en la eliminación de los fragmentos antiguos tras publicar los
nuevos, para fijar el contrato de recuperación:
1. Si falla el borrado de los fragmentos antiguos, se intenta retirar la versión
   nueva y la fuente previa PERMANECE ÍNTEGRA; la operación falla cerrada
   (KnowledgeStoreUnavailable), nunca se declara éxito.
2. Si además falla el rollback (retirada de la versión nueva), se sigue
   fallando cerrada y no se oculta el estado ambiguo; requiere reconciliación
   manual (documentado en el código y en la incidencia).

No es una prueba E2E: usa un doble en memoria. La evidencia E2E vive en
tests/test_rag_qdrant_e2e.py (ARC-04).
"""
import unittest
from unittest.mock import AsyncMock, patch

from qdrant_client import models

from rag import service
from tests.fake_qdrant import FakeQdrantClient


class FailingDeleteClient(FakeQdrantClient):
    """FakeQdrantClient que falla en llamadas PointIdsList según la configuración."""

    def __init__(self, fail_first_ids_delete=False, fail_all_ids_deletes=False):
        super().__init__()
        self.fail_first_ids_delete = fail_first_ids_delete
        self.fail_all_ids_deletes = fail_all_ids_deletes
        self.ids_delete_calls = []

    def delete(self, collection_name, points_selector=None, **kwargs):
        if isinstance(points_selector, models.PointIdsList):
            ids = [str(point_id) for point_id in points_selector.points]
            self.ids_delete_calls.append(ids)
            if self.fail_all_ids_deletes:
                raise RuntimeError("fallo inyectado: todas las eliminaciones por ID")
            if self.fail_first_ids_delete and len(self.ids_delete_calls) == 1:
                raise RuntimeError("fallo inyectado: retirada de fragmentos anteriores")
        return super().delete(collection_name, points_selector=points_selector, **kwargs)


class ReplaceSourceRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = FailingDeleteClient()
        self.collection = "rag_rollback_test"
        self.client_ref = service.client
        self.collection_ref = service.settings.qdrant_collection
        self.checked_ref = service._collection_checked_at
        service.client = self.client
        service.settings.qdrant_collection = self.collection
        service._collection_checked_at = -service._COLLECTION_CHECK_INTERVAL_SECONDS
        self.embedding = [1.0] + [0.0] * (service.settings.embed_dimension - 1)
        self.embed_patch = patch.object(service, "embed", new=AsyncMock(return_value=self.embedding))
        self.embed_patch.start()

        async def run_in_test_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        self.thread_patch = patch.object(service.asyncio, "to_thread", new=run_in_test_thread)
        self.thread_patch.start()

    async def asyncTearDown(self):
        self.thread_patch.stop()
        self.embed_patch.stop()
        service.client = self.client_ref
        service.settings.qdrant_collection = self.collection_ref
        service._collection_checked_at = self.checked_ref
        self.client.close()

    async def _seed_source(self, source_id):
        chunks = await service.ingest_text(
            "Contenido original de la fuente antes de la sustitución.",
            "manual-rollback", "project-rollback", source_id=source_id,
        )
        self.assertEqual(chunks, 1)
        old_points = [p for p in self.client.points.values() if p.payload.get("source_id") == source_id]
        self.assertEqual(len(old_points), 1)
        return {p.id for p in old_points}

    async def test_cleanup_failure_rolls_back_new_version_and_keeps_old(self):
        source_id = "12345678-1234-5678-1234-567812345678"
        old_ids = await self._seed_source(source_id)
        self.client.fail_first_ids_delete = True

        with self.assertRaises(service.KnowledgeStoreUnavailable):
            await service.replace_source(
                source_id, "Contenido nuevo que debe revertirse al fallar la limpieza.",
                "manual-rollback-v2", "project-rollback",
            )

        self.assertEqual(len(self.client.ids_delete_calls), 2)
        self.assertEqual(set(self.client.ids_delete_calls[0]), old_ids)
        remaining = {p.id for p in self.client.points.values()}
        self.assertTrue(old_ids <= remaining, "los fragmentos previos deben permanecer intactos")
        self.assertFalse(
            {p.id for p in self.client.points.values()} - old_ids,
            "la versión nueva debe haberse retirado en el rollback",
        )

    async def test_cleanup_and_rollback_failure_still_fails_closed(self):
        source_id = "87654321-4321-8765-4321-876543218765"
        await self._seed_source(source_id)
        self.client.fail_all_ids_deletes = True

        with self.assertRaises(service.KnowledgeStoreUnavailable):
            await service.replace_source(
                source_id, "Contenido nuevo con doble fallo inyectado.",
                "manual-rollback-v3", "project-rollback",
            )

        self.assertEqual(len(self.client.ids_delete_calls), 2)
        self.assertEqual(self.client.ids_delete_calls[0] is not None, True)
        remaining = list(self.client.points.values())
        self.assertTrue(any(p.payload.get("text") == "Contenido original de la fuente antes de la sustitución." for p in remaining))


if __name__ == "__main__":
    unittest.main()
