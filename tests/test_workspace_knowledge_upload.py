import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile

from api.workspace_routes import workspace_upload_knowledge_document


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
