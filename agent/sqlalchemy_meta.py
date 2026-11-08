"""Adaptador MetaStore para SQLAlchemy Engine con conexión DB-API por operación.

No conserva conexiones del pool entre peticiones ni comparte cursores. Cada query/execute
abre una conexión prestada por el pool, finaliza su transacción y la devuelve al pool.
Diseñado para PostgreSQL/psycopg, igual que el MetaStore de producción.
"""
import asyncio
import hashlib
from contextlib import asynccontextmanager, contextmanager

from rag.meta import MetaStore


class SqlAlchemyMetaStore(MetaStore):
    """MetaStore respaldado por un Engine SQLAlchemy.

    MetaStore conserva su API y sus consultas parametrizadas con '?'.
    Este adaptador usa el DB-API subyacente de psycopg (%s) y obtiene una
    conexión independiente del pool para cada operación.
    """

    def __init__(self, engine):
        self.engine = engine
        # MetaStore solo necesita estos atributos para sus métodos SQL.
        super().__init__(conn=None, placeholder="%s")

    @staticmethod
    def _project_lock_key(project_id: str) -> int:
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id es obligatorio")
        digest = hashlib.blake2b(
            b"axyron:rag:project:" + project_id.encode("utf-8"), digest_size=8
        ).digest()
        return int.from_bytes(digest, byteorder="big", signed=True)

    @staticmethod
    def _try_project_lock(connection, lock_key: int) -> bool:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            acquired = bool(cursor.fetchone()[0])
            connection.commit()
            return acquired
        except BaseException:
            connection.rollback()
            raise
        finally:
            cursor.close()

    @staticmethod
    def _release_project_lock(connection, lock_key: int) -> bool:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
            released = bool(cursor.fetchone()[0])
            connection.commit()
            return released
        except BaseException:
            connection.rollback()
            raise
        finally:
            cursor.close()

    @asynccontextmanager
    async def project_lock(self, project_id: str, timeout_seconds: float = 30.0):
        """Bloqueo advisory de sesión PostgreSQL compartido entre procesos/workers.

        La conexión permanece reservada del pool durante la sección crítica. El
        lock se libera explícitamente; si la liberación falla, se invalida la
        conexión para impedir que vuelva al pool conservando el lock.
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo")
        lock_key = self._project_lock_key(project_id)
        connection = await asyncio.to_thread(self.engine.raw_connection)
        acquired = False
        reusable = True
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        try:
            while not acquired:
                acquired = await asyncio.to_thread(
                    self._try_project_lock, connection, lock_key
                )
                if acquired:
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("Tiempo agotado esperando el bloqueo RAG del proyecto")
                await asyncio.sleep(0.05)
            yield
        except BaseException:
            raise
        finally:
            if acquired:
                try:
                    released = await asyncio.to_thread(
                        self._release_project_lock, connection, lock_key
                    )
                    if not released:
                        reusable = False
                except BaseException:
                    reusable = False
            if not reusable:
                invalidate = getattr(connection, "invalidate", None)
                if callable(invalidate):
                    try:
                        await asyncio.to_thread(invalidate)
                    except Exception:
                        pass
            await asyncio.to_thread(connection.close)

    @contextmanager
    def _tx(self):
        conn = self.engine.raw_connection()
        cur = None
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            # Una excepción al cerrar el cursor no debe dejar la conexión prestada
            # fuera del pool. El cierre de la conexión siempre se intenta.
            try:
                if cur is not None:
                    cur.close()
            finally:
                conn.close()
