"""
Database setup with SQLAlchemy 2.0.

- `engine`     : the connection pool to Postgres.
- `SessionLocal`: a factory that creates DB sessions (one per request).
- `Base`       : the parent class all ORM models inherit from.
- `get_db`     : a FastAPI dependency that yields a session and always closes it.

We use the SYNCHRONOUS SQLAlchemy API on purpose. Row-level locking
(`SELECT ... FOR UPDATE`), which is the heart of this project's concurrency
handling, is simplest and most predictable with sync sessions + a thread pool
(FastAPI runs sync route handlers in a worker thread automatically).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# `pool_pre_ping` checks a connection is alive before using it (avoids errors
# from connections dropped by Postgres after idle timeouts).
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


def get_db():
    """
    FastAPI dependency. Usage in a route:  db: Session = Depends(get_db)
    Yields a session for the duration of the request, then guarantees it closes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
