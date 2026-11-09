"""Aislamiento de la base de datos en la suite de pruebas.

Sin este guardarraíl, ejecutar `pytest` sin `DATABASE_URL` exporta el motor
desde `.env` (PostgreSQL real) y cualquier prueba unitaria que toque persistencia
puede intentar conectarse a la base de datos de producción, exponiendo además
credenciales en los tracebacks de psycopg.

Regla: si el entorno ya define `DATABASE_URL` (p. ej. CI con sqlite, o un
desarrollador con PostgreSQL efímero), se respeta; si no, la suite entera
(linking API + stores) queda ligada a un SQLite temporal, jamás al `.env`.

Lo mismo aplica a los interruptores peligrosos: sin esta protección, el `.env`
real de producción (con AUTH/BILLING/QVAPAY/SANDBOX habilitados) los inyectaría
en los tests; el entorno puede activarlos explícitamente en CI.
"""
import os
import tempfile

if "DATABASE_URL" not in os.environ:
    _tmpdir = tempfile.mkdtemp(prefix="axyron-pytest-default-")
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmpdir, 'test.db')}"
    os.environ["AXYRON_TEST_DEFAULT_DB"] = "sqlite"

for _flag, _default in (
    ("BILLING_ENFORCEMENT_ENABLED", "false"),
    ("QVAPAY_ENABLED", "false"),
    ("SANDBOX_DOCKER_ENABLED", "false"),
):
    os.environ.setdefault(_flag, _default)
