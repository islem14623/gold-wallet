import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def create_database_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return create_engine(database_url, pool_pre_ping=True)
