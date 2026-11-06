"""Database engine compartido de AXION."""
from sqlalchemy import create_engine
from api.config import settings

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
