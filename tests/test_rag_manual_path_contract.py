import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import rag.service as service


class ManualRagPayloadContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_ingest_emits_project_and_path_contract(self):
        source_id = "12345678-1234-5678-1234-567812345678"

        @asynccontextmanager
        async def no_op_lock(_project_id):
            yield

        async def inline_to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        with (
            patch.object(service, "_project_mutation_lock", no_op_lock),
            patch.object(service, "ensure_collection"),
            patch.object(service, "embed", new=AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])),
            patch.object(service.client, "upsert") as upsert,
            patch.object(service.asyncio, "to_thread", new=inline_to_thread),
        ):
            await service.ingest_text(
                "Documentación pública y válida",
                "manual",
                "project-a",
                source_id=source_id,
            )

        payload = upsert.call_args.kwargs["points"][0].payload
        self.assertEqual(payload["project_id"], "project-a")
        self.assertEqual(payload["path"], f"manual/{source_id}")
        self.assertEqual(payload["source_id"], source_id)


if __name__ == "__main__":
    unittest.main()
