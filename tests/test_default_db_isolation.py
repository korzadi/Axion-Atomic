"""Regresión: la suite nunca puede ligarse a la base de datos real por defecto.

`tests/conftest.py` fuerza un SQLite temporal cuando el entorno no define
`DATABASE_URL`. Este test fija ese contrato: sin esa guardia, `pytest` sin
variables de entorno leía `.env` y psycopg llegaba a intentar una conexión a
PostgreSQL de producción (y filtraba credenciales en el traceback).
"""
import os

from api.config import settings


def test_default_database_is_isolated_sqlite():
    if os.environ.get("AXYRON_TEST_DEFAULT_DB") == "sqlite":
        assert settings.database_url.startswith("sqlite")
    else:
        # El entorno eligió deliberadamente DATABASE_URL (p. ej. PostgreSQL
        # efímero de CI); el guardarraíl no aplica.
        assert "DATABASE_URL" in os.environ
