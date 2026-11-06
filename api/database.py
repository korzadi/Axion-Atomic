"""Database engine compartido con pool acotado y comprobación de conexiones."""
from sqlalchemy import create_engine
from api.config import settings

engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    pool_size=max(1, settings.db_pool_size),
    max_overflow=max(0, settings.db_max_overflow),
    pool_timeout=max(1.0, settings.db_pool_timeout_seconds),
    pool_recycle=max(60, settings.db_pool_recycle_seconds),
)
