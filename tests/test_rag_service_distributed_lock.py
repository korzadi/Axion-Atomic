import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import rag.service as service


class ManualRagDistributedLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_mutation_lock_uses_shared_postgres_project_lock(self):
        entered = []

        class FakeStore:
            @asynccontextmanager
            async def project_lock(self, project_id):
                entered.append(("acquire", project_id))
                try:
                    yield
                finally:
                    entered.append(("release", project_id))

        fake_engine = object()
        with (
            patch("api.database.engine", fake_engine),
            patch("agent.sqlalchemy_meta.SqlAlchemyMetaStore", return_value=FakeStore()) as adapter,
        ):
            async with service._project_mutation_lock("project-a"):
                self.assertEqual(entered, [("acquire", "project-a")])

        adapter.assert_called_once_with(fake_engine)
        self.assertEqual(entered, [("acquire", "project-a"), ("release", "project-a")])

    async def test_ingest_holds_project_lock_for_embedding_and_qdrant_write(self):
        state = {"locked": False, "events": []}

        @asynccontextmanager
        async def project_lock(project_id):
            state["events"].append(("lock", project_id))
            state["locked"] = True
            try:
                yield
            finally:
                state["locked"] = False
                state["events"].append(("unlock", project_id))

        async def inline_to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        async def embed(_chunk):
            self.assertTrue(state["locked"])
            state["events"].append(("embed", "project-a"))
            return [0.1, 0.2, 0.3, 0.4]

        def upsert(**_kwargs):
            self.assertTrue(state["locked"])
            state["events"].append(("upsert", "project-a"))

        with (
            patch.object(service, "_project_mutation_lock", project_lock),
            patch.object(service, "ensure_collection"),
            patch.object(service, "embed", side_effect=embed),
            patch.object(service.client, "upsert", side_effect=upsert),
            patch.object(service.asyncio, "to_thread", new=inline_to_thread),
        ):
            count = await service.ingest_text("Contenido público de prueba", "manual", "project-a")

        self.assertEqual(count, 1)
        self.assertEqual(state["events"], [
            ("lock", "project-a"), ("embed", "project-a"),
            ("upsert", "project-a"), ("unlock", "project-a"),
        ])


    async def test_replace_and_delete_are_inside_the_same_project_lock(self):
        events = []

        @asynccontextmanager
        async def project_lock(project_id):
            events.append(("lock", project_id))
            try:
                yield
            finally:
                events.append(("unlock", project_id))

        source_id = "12345678-1234-5678-1234-567812345678"
        old_point = type("Point", (), {
            "id": "old-point",
            "payload": {"project_id": "project-a", "source_id": source_id},
        })()

        async def inline_to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        with (
            patch.object(service, "_project_mutation_lock", project_lock),
            patch.object(service, "ensure_collection"),
            patch.object(service.client, "scroll", return_value=([old_point], None)),
            patch.object(service, "embed", new=AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])),
            patch.object(service.client, "upsert", side_effect=lambda **_: events.append(("upsert", "project-a"))),
            patch.object(service.client, "delete", side_effect=lambda **_: events.append(("delete", "project-a"))),
            patch.object(service.asyncio, "to_thread", new=inline_to_thread),
        ):
            await service.replace_source(source_id, "Nuevo contenido válido", "manual-v2", "project-a")
            await service.delete_source(source_id, "project-a")

        self.assertEqual(events, [
            ("lock", "project-a"), ("upsert", "project-a"),
            ("delete", "project-a"), ("unlock", "project-a"),
            ("lock", "project-a"), ("delete", "project-a"),
            ("unlock", "project-a"),
        ])

    async def test_sensitive_content_is_rejected_before_project_lock(self):
        lock = AsyncMock()
        with patch.object(service, "_project_mutation_lock", lock):
            with self.assertRaises(service.SensitiveContentError):
                await service.ingest_text(
                    'API_TOKEN = "AKIAABCDEFGHIJKLMNOP"', "manual", "project-a"
                )
        lock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
