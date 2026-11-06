import unittest
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


if __name__ == "__main__":
    unittest.main()
