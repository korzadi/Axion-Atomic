import asyncio
import unittest

from rag.indexer import RepoIndexer


class FakeMeta:
    def __init__(self):
        self.ids = {"p1": {"canonical"}, "p2": set()}

    def list_project_chunk_ids(self, project_id):
        return set(self.ids.get(project_id, set()))


class FakeStore:
    def __init__(self):
        self.ids = {"p1": {"canonical", "orphan"}, "p2": set()}
        self.deleted = []

    async def list_project_ids(self, project_id):
        return set(self.ids.get(project_id, set()))

    async def delete_ids(self, ids):
        self.deleted.extend(ids)
        for project_id in self.ids:
            self.ids[project_id].difference_update(ids)


class ReconciliationConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.meta = FakeMeta()
        self.store = FakeStore()
        self.indexer = RepoIndexer(object(), self.store, self.meta)

    async def test_public_reconciliation_waits_for_project_lock(self):
        lock = self.indexer._locks.setdefault("p1", asyncio.Lock())
        await lock.acquire()
        task = asyncio.create_task(self.indexer.reconcile_project("p1"))
        try:
            await asyncio.sleep(0)
            self.assertFalse(task.done(), "reconcile debe esperar a que termine la mutación del proyecto")
            self.assertEqual(self.store.deleted, [])
        finally:
            lock.release()

        self.assertEqual(await task, 1)
        self.assertEqual(self.store.deleted, ["orphan"])

    async def test_internal_reconciliation_runs_under_existing_project_lock(self):
        lock = self.indexer._locks.setdefault("p1", asyncio.Lock())
        async with lock:
            removed = await self.indexer._reconcile_project("p1")
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.deleted, ["orphan"])

    async def test_reconciliation_locks_are_isolated_per_project(self):
        p1_lock = self.indexer._locks.setdefault("p1", asyncio.Lock())
        await p1_lock.acquire()
        try:
            self.assertEqual(await asyncio.wait_for(self.indexer.reconcile_project("p2"), timeout=1), 0)
        finally:
            p1_lock.release()


if __name__ == "__main__":
    unittest.main()