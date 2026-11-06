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


class SqlAlchemyMetaStoreTests(unittest.TestCase):
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
