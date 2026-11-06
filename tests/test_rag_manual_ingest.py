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
            self.assertTrue(kwargs["points"][0].payload["source_id"])
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


    async def test_delete_source_uses_project_and_source_filters(self):
        source_id = "12345678-1234-5678-1234-567812345678"
        with patch.object(service, "ensure_collection"), patch.object(service.client, "delete") as delete:
            await service.delete_source(source_id, "project-a")
        kwargs = delete.call_args.kwargs
        conditions = kwargs["points_selector"].filter.must
        self.assertEqual([(item.key, item.match.value) for item in conditions], [
            ("project_id", "project-a"), ("source_id", source_id)
        ])
        self.assertTrue(kwargs["wait"])

    async def test_delete_source_rejects_invalid_uuid_before_store_access(self):
        with patch.object(service.client, "delete") as delete:
            with self.assertRaisesRegex(ValueError, "UUID válido"):
                await service.delete_source("not-a-uuid", "project-a")
        delete.assert_not_called()

    async def test_delete_source_store_failure_is_safe(self):
        with patch.object(service, "ensure_collection"), patch.object(service.client, "delete", side_effect=RuntimeError("private qdrant endpoint")):
            with self.assertRaises(service.KnowledgeStoreUnavailable) as caught:
                await service.delete_source("12345678-1234-5678-1234-567812345678", "project-a")
        self.assertEqual(str(caught.exception), "El almacén de conocimiento no está disponible")
        self.assertNotIn("private qdrant endpoint", str(caught.exception))


    async def test_list_sources_groups_fragments_and_never_returns_document_text(self):
        from types import SimpleNamespace
        pages = [
            ([SimpleNamespace(payload={"project_id": "project-a", "source_id": "id-1", "source": "manual", "chunk": 0}),
              SimpleNamespace(payload={"project_id": "project-a", "source_id": "id-1", "source": "manual", "chunk": 1}),
              SimpleNamespace(payload={"project_id": "project-b", "source_id": "id-2", "source": "private", "text": "secret"})], None)
        ]
        with patch.object(service, "ensure_collection"), patch.object(service.client, "scroll", return_value=pages[0]) as scroll:
            result = await service.list_sources("project-a")
        self.assertEqual(result["sources"], [{"source_id": "id-1", "source": "manual", "chunks": 2, "legacy": False}])
        self.assertFalse(result["truncated"])
        self.assertNotIn("secret", str(result))
        self.assertEqual(scroll.call_args.kwargs["with_vectors"], False)

    async def test_list_sources_marks_legacy_documents_without_delete_id(self):
        from types import SimpleNamespace
        page = ([SimpleNamespace(payload={"project_id": "project-a", "source": "old-upload", "chunk": 0})], None)
        with patch.object(service, "ensure_collection"), patch.object(service.client, "scroll", return_value=page):
            result = await service.list_sources("project-a")
        self.assertEqual(result["sources"][0]["source_id"], None)
        self.assertTrue(result["sources"][0]["legacy"])

    async def test_list_sources_rejects_invalid_limit_before_qdrant(self):
        with patch.object(service.client, "scroll") as scroll:
            with self.assertRaises(ValueError):
                await service.list_sources("project-a", limit=101)
        scroll.assert_not_called()


    async def test_replace_source_publishes_new_chunks_then_retires_old_ids(self):
        from types import SimpleNamespace
        source_id = "12345678-1234-5678-1234-567812345678"
        old = SimpleNamespace(id="old-point", payload={"project_id": "project-a", "source_id": source_id})
        calls = []
        def scroll(**kwargs):
            return ([old], None)
        def upsert(**kwargs):
            calls.append(("upsert", kwargs))
        def delete(**kwargs):
            calls.append(("delete", kwargs))
        with patch.object(service, "ensure_collection"), patch.object(service.client, "scroll", side_effect=scroll), patch.object(service, "embed", AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])), patch.object(service.client, "upsert", side_effect=upsert), patch.object(service.client, "delete", side_effect=delete):
            count = await service.replace_source(source_id, "Nuevo contenido válido", "manual-v2", "project-a")
        self.assertEqual(count, 1)
        self.assertEqual([call[0] for call in calls], ["upsert", "delete"])
        self.assertEqual(calls[1][1]["points_selector"].points, ["old-point"])

    async def test_replace_source_keeps_old_chunks_when_embedding_fails(self):
        from types import SimpleNamespace
        source_id = "12345678-1234-5678-1234-567812345678"
        old = SimpleNamespace(id="old-point", payload={"project_id": "project-a", "source_id": source_id})
        with patch.object(service, "ensure_collection"), patch.object(service.client, "scroll", return_value=([old], None)), patch.object(service, "embed", AsyncMock(side_effect=RuntimeError("private embed endpoint"))), patch.object(service.client, "upsert") as upsert, patch.object(service.client, "delete") as delete:
            with self.assertRaises(service.EmbeddingServiceUnavailable):
                await service.replace_source(source_id, "Nuevo contenido válido", "manual-v2", "project-a")
        upsert.assert_not_called()
        delete.assert_not_called()

    async def test_replace_source_refuses_source_from_another_project(self):
        source_id = "12345678-1234-5678-1234-567812345678"
        with patch.object(service, "ensure_collection"), patch.object(service.client, "scroll", return_value=([], None)), patch.object(service.client, "upsert") as upsert:
            with self.assertRaisesRegex(ValueError, "No se encontró"):
                await service.replace_source(source_id, "Nuevo contenido válido", "manual-v2", "project-a")
        upsert.assert_not_called()



    async def test_replace_source_rolls_back_new_chunks_if_retiring_old_chunks_fails(self):
        from types import SimpleNamespace

        source_id = "12345678-1234-5678-1234-567812345678"
        old = SimpleNamespace(id="old-point", payload={"project_id": "project-a", "source_id": source_id})
        delete_calls = []

        def delete(**kwargs):
            delete_calls.append(kwargs)
            if len(delete_calls) == 1:
                raise RuntimeError("private qdrant endpoint")

        with (
            patch.object(service, "ensure_collection"),
            patch.object(service.client, "scroll", return_value=([old], None)),
            patch.object(service, "embed", AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])),
            patch.object(service.client, "upsert") as upsert,
            patch.object(service.client, "delete", side_effect=delete),
        ):
            with self.assertRaises(service.KnowledgeStoreUnavailable):
                await service.replace_source(source_id, "Nuevo contenido válido", "manual-v2", "project-a")

        self.assertEqual(upsert.call_count, 1)
        self.assertEqual(len(delete_calls), 2)
        self.assertEqual(delete_calls[0]["points_selector"].points, ["old-point"])
        new_ids = [point.id for point in upsert.call_args.kwargs["points"]]
        self.assertEqual(delete_calls[1]["points_selector"].points, new_ids)

    async def test_replace_source_does_not_delete_old_chunks_if_new_publish_fails(self):
        from types import SimpleNamespace

        source_id = "12345678-1234-5678-1234-567812345678"
        old = SimpleNamespace(id="old-point", payload={"project_id": "project-a", "source_id": source_id})
        with (
            patch.object(service, "ensure_collection"),
            patch.object(service.client, "scroll", return_value=([old], None)),
            patch.object(service, "embed", AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])),
            patch.object(service.client, "upsert", side_effect=RuntimeError("private qdrant endpoint")),
            patch.object(service.client, "delete") as delete,
        ):
            with self.assertRaises(service.KnowledgeStoreUnavailable):
                await service.replace_source(source_id, "Nuevo contenido válido", "manual-v2", "project-a")

        delete.assert_not_called()

    async def test_list_sources_store_failure_returns_safe_error(self):
        with (
            patch.object(service, "ensure_collection"),
            patch.object(service.client, "scroll", side_effect=RuntimeError("private qdrant endpoint")),
        ):
            with self.assertRaises(service.KnowledgeStoreUnavailable) as caught:
                await service.list_sources("project-a")
        self.assertEqual(str(caught.exception), "El almacén de conocimiento no está disponible")
        self.assertNotIn("private qdrant endpoint", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
