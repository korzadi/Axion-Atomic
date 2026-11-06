"""Adaptador MetaStore para SQLAlchemy Engine con conexión DB-API por operación.

No conserva conexiones del pool entre peticiones ni comparte cursores. Cada query/execute
abre una conexión prestada por el pool, finaliza su transacción y la devuelve al pool.
Diseñado para PostgreSQL/psycopg, igual que el MetaStore de producción.
"""
from contextlib import contextmanager

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
            if cur is not None:
                cur.close()
            conn.close()
