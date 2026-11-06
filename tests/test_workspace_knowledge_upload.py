import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile

from api.workspace_routes import (
    workspace_upload_knowledge_document,
    workspace_list_knowledge_sources,
    workspace_delete_knowledge_source,
)


class KnowledgeUploadRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_authorizes_before_reading_or_indexing(self):
        upload = UploadFile(filename="secret.txt", file=io.BytesIO(b"private"))
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.extract_document") as extract,
            patch("api.workspace_routes.ingest_text", new=AsyncMock()) as ingest,
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_upload_knowledge_document("foreign", upload, {"id": "u"})
        self.assertEqual(caught.exception.status_code, 404)
        extract.assert_not_called()
        ingest.assert_not_awaited()

    async def test_upload_indexes_extracted_text_with_project_and_source_id(self):
        upload = UploadFile(filename="notes.txt", file=io.BytesIO(b"hello"))
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.extract_document", return_value=("hello", "notes.txt")),
            patch("api.workspace_routes.ingest_text", new=AsyncMock(return_value=1)) as ingest,
        ):
            result = await workspace_upload_knowledge_document("project-a", upload, {"id": "u"})
        self.assertEqual(result["status"], "indexed")
        self.assertEqual(result["source"], "notes.txt")
        self.assertEqual(result["chunks"], 1)
        self.assertEqual(ingest.await_args.args[:3], ("hello", "notes.txt", "project-a"))
        self.assertEqual(ingest.await_args.kwargs["source_id"], result["source_id"])

    async def test_upload_rejects_oversized_file_and_closes_stream(self):
        upload = UploadFile(filename="large.txt", file=io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)))
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.ingest_text", new=AsyncMock()) as ingest,
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_upload_knowledge_document("project-a", upload, {"id": "u"})
        self.assertEqual(caught.exception.status_code, 422)
        self.assertTrue(upload.file.closed)
        ingest.assert_not_awaited()

    async def test_upload_maps_embedding_outage_to_503_and_closes_stream(self):
        from rag.service import EmbeddingServiceUnavailable

        upload = UploadFile(filename="notes.txt", file=io.BytesIO(b"hello"))
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.extract_document", return_value=("hello", "notes.txt")),
            patch("api.workspace_routes.ingest_text", new=AsyncMock(side_effect=EmbeddingServiceUnavailable("embedding unavailable"))),
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_upload_knowledge_document("project-a", upload, {"id": "u"})
        self.assertEqual(caught.exception.status_code, 503)
        self.assertTrue(upload.file.closed)


    async def test_upload_maps_document_parser_errors_to_422_and_closes_stream(self):
        from rag.document_loader import DocumentLoadError

        upload = UploadFile(filename="broken.pdf", file=io.BytesIO(b"not a pdf"))
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.extract_document", side_effect=DocumentLoadError("PDF inválido")),
            patch("api.workspace_routes.ingest_text", new=AsyncMock()) as ingest,
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_upload_knowledge_document("project-a", upload, {"id": "u"})
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail, "PDF inválido")
        self.assertTrue(upload.file.closed)
        ingest.assert_not_awaited()

    async def test_source_listing_is_project_scoped_and_read_only_for_viewers(self):
        expected = {"sources": [{"source_id": "id-1", "source": "manual", "chunks": 2, "legacy": False}], "truncated": False}
        with (
            patch("api.workspace_routes._project_role") as authorize,
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.list_sources", new=AsyncMock(return_value=expected)) as listing,
        ):
            result = await workspace_list_knowledge_sources("project-a", 50, {"id": "viewer"})
        authorize.assert_called_once_with({"id": "viewer"}, "project-a", ("owner", "admin", "editor", "viewer"))
        listing.assert_awaited_once_with("project-a", limit=50)
        self.assertEqual(result["project_id"], "project-a")
        self.assertEqual(result["sources"], expected["sources"])

    async def test_source_listing_denies_non_members_before_store_access(self):
        denied = HTTPException(status_code=404, detail="Proyecto no encontrado")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.list_sources", new=AsyncMock()) as listing,
        ):
            with self.assertRaises(HTTPException):
                await workspace_list_knowledge_sources("foreign", 100, {"id": "outsider"})
        listing.assert_not_awaited()

    async def test_source_deletion_requires_editor_before_store_access(self):
        denied = HTTPException(status_code=403, detail="Permiso insuficiente")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied) as authorize,
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.delete_source", new=AsyncMock()) as deletion,
        ):
            with self.assertRaises(HTTPException):
                await workspace_delete_knowledge_source(
                    "12345678-1234-5678-1234-567812345678", "project-a", {"id": "viewer"}
                )
        authorize.assert_called_once_with({"id": "viewer"}, "project-a", ("owner", "admin", "editor"))
        deletion.assert_not_awaited()

    async def test_source_deletion_uses_exact_project_and_source_id(self):
        source_id = "12345678-1234-5678-1234-567812345678"
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.delete_source", new=AsyncMock()) as deletion,
        ):
            result = await workspace_delete_knowledge_source(source_id, "project-a", {"id": "editor"})
        deletion.assert_awaited_once_with(source_id, "project-a")
        self.assertEqual(result, {"status": "deleted", "project_id": "project-a", "source_id": source_id})


    async def test_source_listing_maps_store_outage_to_503(self):
        from rag.service import KnowledgeStoreUnavailable

        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.list_sources", new=AsyncMock(side_effect=KnowledgeStoreUnavailable("safe unavailable"))),
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_list_knowledge_sources("project-a", 100, {"id": "viewer"})
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "safe unavailable")

    async def test_source_deletion_maps_store_outage_to_503(self):
        from rag.service import KnowledgeStoreUnavailable

        source_id = "12345678-1234-5678-1234-567812345678"
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.delete_source", new=AsyncMock(side_effect=KnowledgeStoreUnavailable("safe unavailable"))),
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_delete_knowledge_source(source_id, "project-a", {"id": "editor"})
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "safe unavailable")

    async def test_source_deletion_rejects_invalid_uuid_without_store_access(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.delete_source", new=AsyncMock(side_effect=ValueError("source_id debe ser un UUID válido"))) as deletion,
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_delete_knowledge_source("not-a-uuid", "project-a", {"id": "editor"})
        self.assertEqual(caught.exception.status_code, 422)
        deletion.assert_awaited_once_with("not-a-uuid", "project-a")


    async def test_source_reindex_requires_editor_before_store_access(self):
        from api.schemas import IngestRequest
        from api.workspace_routes import workspace_replace_knowledge_source

        denied = HTTPException(status_code=403, detail="Permiso insuficiente")
        with (
            patch("api.workspace_routes._project_role", side_effect=denied) as authorize,
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.replace_source", new=AsyncMock()) as replace,
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_replace_knowledge_source(
                    "12345678-1234-5678-1234-567812345678",
                    IngestRequest(project_id="project-a", text="texto", source="manual"),
                    {"id": "viewer"},
                )
        self.assertEqual(caught.exception.status_code, 403)
        authorize.assert_called_once()
        replace.assert_not_awaited()

    async def test_source_reindex_uses_exact_project_and_source_id(self):
        from api.schemas import IngestRequest
        from api.workspace_routes import workspace_replace_knowledge_source

        source_id = "12345678-1234-5678-1234-567812345678"
        request = IngestRequest(project_id="project-a", text="contenido nuevo", source="manual-v2")
        with (
            patch("api.workspace_routes._project_role") as authorize,
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.replace_source", new=AsyncMock(return_value=3)) as replace,
        ):
            result = await workspace_replace_knowledge_source(source_id, request, {"id": "editor"})
        authorize.assert_called_once_with({"id": "editor"}, "project-a", ("owner", "admin", "editor"))
        replace.assert_awaited_once_with(source_id, "contenido nuevo", "manual-v2", "project-a")
        self.assertEqual(result, {"status": "reindexed", "project_id": "project-a", "source_id": source_id, "chunks": 3})

    async def test_source_reindex_maps_missing_source_and_store_outage(self):
        from api.schemas import IngestRequest
        from api.workspace_routes import workspace_replace_knowledge_source
        from rag.service import KnowledgeStoreUnavailable

        request = IngestRequest(project_id="project-a", text="contenido nuevo", source="manual")
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.replace_source", new=AsyncMock(side_effect=ValueError("No se encontró la fuente"))),
        ):
            with self.assertRaises(HTTPException) as missing:
                await workspace_replace_knowledge_source("12345678-1234-5678-1234-567812345678", request, {"id": "editor"})
        self.assertEqual(missing.exception.status_code, 404)

        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.replace_source", new=AsyncMock(side_effect=KnowledgeStoreUnavailable("safe unavailable"))),
        ):
            with self.assertRaises(HTTPException) as unavailable:
                await workspace_replace_knowledge_source("12345678-1234-5678-1234-567812345678", request, {"id": "editor"})
        self.assertEqual(unavailable.exception.status_code, 503)
