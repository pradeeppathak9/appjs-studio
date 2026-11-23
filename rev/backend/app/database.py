from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Pool is per process: 4 uvicorn workers + celery children each get their own.
# Keep (pool_size + max_overflow) * processes well under Postgres max_connections (200).
engine = create_engine(settings.database_url, pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
