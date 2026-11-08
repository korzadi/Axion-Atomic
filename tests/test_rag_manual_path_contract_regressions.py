import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import rag.service as service


class ManualRagPathContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_replacement_keeps_shared_path_contract(self):
        source_id = "12345678-1234-5678-1234-567812345678"
        old = SimpleNamespace(
            id="old-point",
            payload={"project_id": "project-a", "source_id": source_id},
        )

        @asynccontextmanager
        async def no_op_lock(_project_id):
            yield

        with (
            patch.object(service, "_project_mutation_lock", no_op_lock),
            patch.object(service, "ensure_collection"),
            patch.object(service.client, "scroll", return_value=([old], None)),
            patch.object(service, "embed", new=AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])),
            patch.object(service.client, "upsert") as upsert,
            patch.object(service.client, "delete"),
        ):
            await service.replace_source(
                source_id,
                "Contenido nuevo y seguro",
                "manual-v2",
                "project-a",
            )

        payload = upsert.call_args.kwargs["points"][0].payload
        self.assertEqual(payload["project_id"], "project-a")
        self.assertEqual(payload["path"], f"manual/{source_id}")
        self.assertEqual(payload["source_id"], source_id)

    async def test_invalid_source_id_is_rejected_before_project_lock(self):
        lock_entered = False

        @asynccontextmanager
        async def forbidden_lock(_project_id):
            nonlocal lock_entered
            lock_entered = True
            raise AssertionError("No debe adquirirse el lock para un UUID inválido")
            yield

        with patch.object(service, "_project_mutation_lock", forbidden_lock):
            with self.assertRaisesRegex(ValueError, "UUID válido"):
                await service.ingest_text(
                    "Contenido seguro",
                    "manual",
                    "project-a",
                    source_id="not-a-uuid",
                )

        self.assertFalse(lock_entered)


if __name__ == "__main__":
    unittest.main()
