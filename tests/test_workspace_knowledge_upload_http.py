"""Pruebas HTTP multipart para la carga de conocimiento del workspace."""
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.workspace_routes import _csrf_user


def enforce_role(user, project_id, allowed):
    if user["role"] not in allowed:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return user["role"]


class WorkspaceKnowledgeUploadHttpTests(unittest.TestCase):
    def setUp(self):
        self.role = "editor"
        self.client = TestClient(app)
        self.admission_patch = patch("api.workspace_routes._enforce_workspace_limit")
        self.admission_patch.start()
        app.dependency_overrides[_csrf_user] = lambda: {
            "id": "upload-user",
            "email": "upload@example.test",
            "display_name": "Upload test",
            "role": self.role,
        }

    def tearDown(self):
        app.dependency_overrides.clear()
        self.admission_patch.stop()

    def test_editor_uploads_multipart_file_and_indexes_in_requested_project(self):
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.extract_document", return_value=("contenido validado", "manual.txt")) as extract,
            patch("api.workspace_routes.ingest_text", new_callable=AsyncMock, return_value=2) as ingest,
        ):
            response = self.client.post(
                "/workspace/knowledge/upload?project_id=project-a",
                files={"file": ("manual.txt", b"contenido validado", "text/plain")},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "indexed")
        self.assertEqual(payload["project_id"], "project-a")
        self.assertEqual(payload["source"], "manual.txt")
        self.assertEqual(payload["chunks"], 2)
        self.assertEqual(ingest.await_args.args[:3], ("contenido validado", "manual.txt", "project-a"))
        self.assertEqual(ingest.await_args.kwargs["source_id"], payload["source_id"])
        extract.assert_called_once_with("manual.txt", b"contenido validado")

    def test_viewer_cannot_upload_or_trigger_document_processing(self):
        self.role = "viewer"
        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.extract_document") as extract,
            patch("api.workspace_routes.ingest_text", new_callable=AsyncMock) as ingest,
        ):
            response = self.client.post(
                "/workspace/knowledge/upload?project_id=private-project",
                files={"file": ("private.txt", b"contenido privado", "text/plain")},
            )

        self.assertEqual(response.status_code, 404)
        extract.assert_not_called()
        ingest.assert_not_awaited()

    def test_unsupported_upload_is_rejected_over_http_without_indexing(self):
        from rag.document_loader import DocumentLoadError

        with (
            patch("api.workspace_routes._project_role", side_effect=enforce_role),
            patch("api.workspace_routes.extract_document", side_effect=DocumentLoadError("Formato no admitido.")),
            patch("api.workspace_routes.ingest_text", new_callable=AsyncMock) as ingest,
        ):
            response = self.client.post(
                "/workspace/knowledge/upload?project_id=project-a",
                files={"file": ("payload.exe", b"not executable", "application/octet-stream")},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Formato no admitido.")
        ingest.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
