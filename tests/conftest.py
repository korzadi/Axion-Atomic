"""Aislamiento de la base de datos en la suite de pruebas.

Sin este guardarraíl, ejecutar `pytest` sin `DATABASE_URL` exporta el motor
desde `.env` (PostgreSQL real) y cualquier prueba unitaria que toque persistencia
puede intentar conectarse a la base de datos de producción, exponiendo además
credenciales en los tracebacks de psycopg.

Regla: si el entorno ya define `DATABASE_URL` (p. ej. CI con sqlite, o un
desarrollador con PostgreSQL efímero), se respeta; si no, la suite entera
(linking API + stores) queda ligada a un SQLite temporal, jamás al `.env`.
"""
import os
import tempfile

if "DATABASE_URL" not in os.environ:
    _tmpdir = tempfile.mkdtemp(prefix="axyron-pytest-default-")
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmpdir, 'test.db')}"
    os.environ["AXYRON_TEST_DEFAULT_DB"] = "sqlite"
