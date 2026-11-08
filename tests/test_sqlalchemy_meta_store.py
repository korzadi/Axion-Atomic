import unittest

from agent.sqlalchemy_meta import SqlAlchemyMetaStore


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 1
        self.closed = False

    def execute(self, sql, params=()):
        self.connection.statements.append((sql, params))
        if self.connection.fail:
            raise RuntimeError("database failure")

    def fetchall(self):
        return [(1,)]

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, fail=False):
        self.fail = fail
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.cursors = []

    def cursor(self):
        cur = Cursor(self)
        self.cursors.append(cur)
        return cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class Engine:
    def __init__(self, failures=()):
        self.failures = list(failures)
        self.connections = []

    def raw_connection(self):
        conn = Connection(self.failures.pop(0) if self.failures else False)
        self.connections.append(conn)
        return conn


class CursorCloseFailure(Cursor):
    def close(self):
        self.closed = True
        raise RuntimeError("cursor close failure")


class ConnectionWithFailingCursorClose(Connection):
    def cursor(self):
        cur = CursorCloseFailure(self)
        self.cursors.append(cur)
        return cur


class EngineWithFailingCursorClose(Engine):
    def raw_connection(self):
        conn = ConnectionWithFailingCursorClose()
        self.connections.append(conn)
        return conn



class AdvisoryLockCursor(Cursor):
    def fetchone(self):
        statement = self.connection.statements[-1][0]
        if "pg_try_advisory_lock" in statement:
            return (self.connection.lock_result,)
        if "pg_advisory_unlock" in statement:
            return (self.connection.unlock_result,)
        raise AssertionError("Consulta advisory lock inesperada")


class AdvisoryLockConnection(Connection):
    def __init__(self, lock_result=True, unlock_result=True):
        super().__init__()
        self.lock_result = lock_result
        self.unlock_result = unlock_result
        self.invalidated = False

    def cursor(self):
        cur = AdvisoryLockCursor(self)
        self.cursors.append(cur)
        return cur

    def invalidate(self):
        self.invalidated = True


class AdvisoryLockEngine(Engine):
    def __init__(self, lock_result=True, unlock_result=True):
        super().__init__()
        self.lock_result = lock_result
        self.unlock_result = unlock_result

    def raw_connection(self):
        conn = AdvisoryLockConnection(self.lock_result, self.unlock_result)
        self.connections.append(conn)
        return conn



import threading


class SharedAdvisoryLockManager:
    def __init__(self):
        self.guard = threading.Lock()
        self.held = set()

    def acquire(self, key):
        with self.guard:
            if key in self.held:
                return False
            self.held.add(key)
            return True

    def release(self, key):
        with self.guard:
            if key not in self.held:
                return False
            self.held.remove(key)
            return True


class SharedAdvisoryCursor(Cursor):
    def fetchone(self):
        sql, params = self.connection.statements[-1]
        key = params[0]
        if "pg_try_advisory_lock" in sql:
            return (self.connection.manager.acquire(key),)
        if "pg_advisory_unlock" in sql:
            return (self.connection.manager.release(key),)
        raise AssertionError("Consulta advisory lock inesperada")


class SharedAdvisoryConnection(Connection):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def cursor(self):
        cur = SharedAdvisoryCursor(self)
        self.cursors.append(cur)
        return cur


class SharedAdvisoryEngine(Engine):
    def __init__(self):
        super().__init__()
        self.manager = SharedAdvisoryLockManager()

    def raw_connection(self):
        conn = SharedAdvisoryConnection(self.manager)
        self.connections.append(conn)
        return conn


class SqlAlchemyMetaStoreTests(unittest.TestCase):
    def test_project_lock_uses_session_advisory_lock_and_releases_connection(self):
        import asyncio

        async def exercise():
            engine = AdvisoryLockEngine()
            store = SqlAlchemyMetaStore(engine)
            async with store.project_lock("project-a"):
                self.assertEqual(len(engine.connections), 1)
                self.assertFalse(engine.connections[0].closed)
            connection = engine.connections[0]
            self.assertTrue(connection.closed)
            self.assertFalse(connection.invalidated)
            self.assertEqual(
                [statement for statement, _ in connection.statements],
                ["SELECT pg_try_advisory_lock(%s)", "SELECT pg_advisory_unlock(%s)"],
            )
            self.assertEqual(
                connection.statements[0][1], connection.statements[1][1]
            )
            self.assertEqual(connection.commits, 2)

        asyncio.run(exercise())

    def test_independent_meta_stores_serialize_the_same_project(self):
        import asyncio

        async def exercise():
            engine = SharedAdvisoryEngine()
            first = SqlAlchemyMetaStore(engine)
            second = SqlAlchemyMetaStore(engine)
            entered = asyncio.Event()

            async def second_worker():
                async with second.project_lock("shared-project", timeout_seconds=2):
                    entered.set()

            async with first.project_lock("shared-project"):
                task = asyncio.create_task(second_worker())
                await asyncio.sleep(0.12)
                self.assertFalse(entered.is_set())

            await asyncio.wait_for(task, timeout=2)
            self.assertTrue(entered.is_set())
            self.assertEqual(len(engine.connections), 2)
            self.assertTrue(all(connection.closed for connection in engine.connections))
            self.assertEqual(engine.manager.held, set())

        asyncio.run(exercise())

    def test_project_lock_invalidates_connection_if_unlock_fails(self):
        import asyncio

        async def exercise():
            engine = AdvisoryLockEngine(unlock_result=False)
            store = SqlAlchemyMetaStore(engine)
            async with store.project_lock("project-a"):
                pass
            connection = engine.connections[0]
            self.assertTrue(connection.invalidated)
            self.assertTrue(connection.closed)

        asyncio.run(exercise())

    def test_project_lock_rejects_invalid_project_and_timeout(self):
        import asyncio

        async def exercise():
            store = SqlAlchemyMetaStore(AdvisoryLockEngine(lock_result=False))
            with self.assertRaises(ValueError):
                async with store.project_lock(" "):
                    pass
            with self.assertRaises(ValueError):
                async with store.project_lock("p1", timeout_seconds=0):
                    pass

        asyncio.run(exercise())

    def test_connection_is_released_after_each_operation(self):
        engine = Engine()
        store = SqlAlchemyMetaStore(engine)

        self.assertEqual(store.query("SELECT id FROM items WHERE id = ?", ("x",)), [(1,)])
        self.assertEqual(store.execute("UPDATE items SET state = ?", ("done",)), 1)

        self.assertEqual(len(engine.connections), 2)
        for conn in engine.connections:
            self.assertTrue(conn.closed)
            self.assertEqual(conn.commits, 1)
            self.assertEqual(conn.rollbacks, 0)
            self.assertTrue(conn.cursors[0].closed)
        self.assertEqual(engine.connections[0].statements[0][0], "SELECT id FROM items WHERE id = %s")

    def test_explicit_transaction_uses_one_connection_and_commits_once(self):
        engine = Engine()
        store = SqlAlchemyMetaStore(engine)

        with store.transaction() as cursor:
            cursor.execute(store.sql("UPDATE items SET state = ?"), ("one",))
            cursor.execute(store.sql("UPDATE items SET state = ?"), ("two",))

        self.assertEqual(len(engine.connections), 1)
        conn = engine.connections[0]
        self.assertEqual(len(conn.statements), 2)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)
        self.assertTrue(conn.closed)
        self.assertTrue(conn.cursors[0].closed)

    def test_connection_is_released_even_if_cursor_close_fails(self):
        engine = EngineWithFailingCursorClose()
        store = SqlAlchemyMetaStore(engine)

        with self.assertRaisesRegex(RuntimeError, "cursor close failure"):
            store.execute("UPDATE items SET state = ?", ("done",))

        conn = engine.connections[0]
        self.assertTrue(conn.cursors[0].closed)
        self.assertTrue(conn.closed)
        self.assertEqual(conn.commits, 1)

    def test_failure_rolls_back_and_releases_connection(self):
        engine = Engine((True,))
        store = SqlAlchemyMetaStore(engine)

        with self.assertRaisesRegex(RuntimeError, "database failure"):
            store.execute("UPDATE items SET state = ?", ("failed",))

        conn = engine.connections[0]
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)
        self.assertTrue(conn.closed)
        self.assertTrue(conn.cursors[0].closed)


if __name__ == "__main__":
    unittest.main()
