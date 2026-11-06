import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import rag.service as service

FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


class ManualIngestSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_secret_in_text_is_rejected_before_embedding_or_qdrant(self):
        embed = AsyncMock(return_value=[[0.1] * 4])
        upsert = patch.object(service.client, "upsert")
        with patch.object(service, "ensure_collection") as ensure, patch.object(service, "embed", embed), upsert as store:
            with self.assertRaises(service.SensitiveContentError) as caught:
                await service.ingest_text(f'API_TOKEN = "{FAKE_AWS}"', "manual", "project-a")
            self.assertNotIn(FAKE_AWS, str(caught.exception))
            ensure.assert_not_called()
            embed.assert_not_awaited()
            store.assert_not_called()

    async def test_secret_in_source_is_rejected_before_embedding_or_qdrant(self):
        embed = AsyncMock(return_value=[[0.1] * 4])
        with patch.object(service, "ensure_collection") as ensure, patch.object(service, "embed", embed), patch.object(service.client, "upsert") as store:
            with self.assertRaises(service.SensitiveContentError):
                await service.ingest_text("Texto público sin credenciales", f'api_key="{FAKE_AWS}"', "project-a")
            ensure.assert_not_called()
            embed.assert_not_awaited()
            store.assert_not_called()

    async def test_safe_text_is_embedded_and_project_scoped_payload_is_saved(self):
        embed = AsyncMock(return_value=[[0.1] * 4])
        with patch.object(service, "ensure_collection"), patch.object(service, "embed", embed), patch.object(service.client, "upsert") as store:
            count = await service.ingest_text("Documentación pública del proyecto", "manual", "project-a")
            self.assertEqual(count, 1)
            embed.assert_awaited_once()
            kwargs = store.call_args.kwargs
            self.assertEqual(kwargs["points"][0].payload["project_id"], "project-a")
            self.assertEqual(kwargs["points"][0].payload["source"], "manual")
            self.assertEqual(kwargs["points"][0].payload["text"], "Documentación pública del proyecto")

    async def test_invalid_size_and_project_are_rejected(self):
        with self.assertRaises(ValueError):
            await service.ingest_text(" " * 10, "manual", "project-a")
        with self.assertRaises(ValueError):
            await service.ingest_text("x" * (service.MAX_MANUAL_INGEST_CHARS + 1), "manual", "project-a")
        with self.assertRaises(ValueError):
            await service.ingest_text("texto válido", "manual", " ")

    async def test_qdrant_sync_calls_run_outside_event_loop_thread(self):
        loop_thread = threading.get_ident()
        call_threads = []

        def record_ensure():
            call_threads.append(threading.get_ident())

        def record_upsert(**kwargs):
            call_threads.append(threading.get_ident())

        embed = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
        with patch.object(service, "ensure_collection", side_effect=record_ensure), patch.object(service, "embed", embed), patch.object(service.client, "upsert", side_effect=record_upsert):
            await service.ingest_text("Texto de documentación segura", "manual", "project-a")

        self.assertEqual(len(call_threads), 2)
        self.assertTrue(all(thread_id != loop_thread for thread_id in call_threads))

    async def test_retrieval_store_failure_is_observable_not_empty_context(self):
        embed = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
        with patch.object(service, "ensure_collection"), patch.object(service, "embed", embed), patch.object(service.client, "query_points", side_effect=RuntimeError("internal endpoint details")):
            with self.assertRaises(service.KnowledgeStoreUnavailable) as caught:
                await service.retrieve("consulta", "project-a")
        self.assertEqual(str(caught.exception), "El almacén de conocimiento no está disponible")
        self.assertNotIn("internal endpoint details", str(caught.exception))

    async def test_retrieval_enforces_project_filter_and_rechecks_payload(self):
        loop_thread = threading.get_ident()
        call_threads = []

        def query_points(**kwargs):
            call_threads.append(threading.get_ident())
            project_filter = kwargs["query_filter"]
            self.assertEqual(project_filter.must[0].key, "project_id")
            self.assertEqual(project_filter.must[0].match.value, "project-a")
            return SimpleNamespace(points=[
                SimpleNamespace(payload={"project_id": "project-a", "source": "manual", "text": "contenido propio"}),
                SimpleNamespace(payload={"project_id": "project-b", "source": "manual", "text": "contenido ajeno"}),
            ])

        embed = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
        with patch.object(service, "ensure_collection"), patch.object(service, "embed", embed), patch.object(service.client, "query_points", side_effect=query_points):
            context = await service.retrieve("consulta", "project-a")

        self.assertIn("contenido propio", context)
        self.assertNotIn("contenido ajeno", context)
        self.assertEqual(len(call_threads), 1)
        self.assertNotEqual(call_threads[0], loop_thread)


    async def test_qdrant_collection_failure_returns_safe_store_error(self):
        with patch.object(service, "ensure_collection", side_effect=RuntimeError("private endpoint")):
            with self.assertRaises(service.KnowledgeStoreUnavailable) as caught:
                await service.ingest_text("Texto seguro", "manual", "project-a")
        self.assertEqual(str(caught.exception), "El almacén de conocimiento no está disponible")
        self.assertNotIn("private endpoint", str(caught.exception))

    async def test_embedding_failure_returns_safe_embedding_error_before_upsert(self):
        with patch.object(service, "ensure_collection"), patch.object(service, "embed", AsyncMock(side_effect=RuntimeError("private model endpoint"))), patch.object(service.client, "upsert") as store:
            with self.assertRaises(service.EmbeddingServiceUnavailable) as caught:
                await service.ingest_text("Texto seguro", "manual", "project-a")
        self.assertEqual(str(caught.exception), "El servicio de embeddings no está disponible")
        self.assertNotIn("private model endpoint", str(caught.exception))
        store.assert_not_called()

    async def test_qdrant_upsert_failure_returns_safe_store_error(self):
        with patch.object(service, "ensure_collection"), patch.object(service, "embed", AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])), patch.object(service.client, "upsert", side_effect=RuntimeError("private qdrant endpoint")):
            with self.assertRaises(service.KnowledgeStoreUnavailable) as caught:
                await service.ingest_text("Texto seguro", "manual", "project-a")
        self.assertEqual(str(caught.exception), "El almacén de conocimiento no está disponible")
        self.assertNotIn("private qdrant endpoint", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
