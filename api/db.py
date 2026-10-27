"""Database engine + session (SQLAlchemy).

DB-agnostic via DATABASE_URL: SQLite by default (zero-ops, fine for the private
family-circle launch), Postgres in production by setting DATABASE_URL — the
models and queries are written to port cleanly.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./api_store/app.db")

# Railway/Heroku hand out postgres:// URLs; SQLAlchemy 2.0 requires postgresql://.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

if DATABASE_URL.startswith("sqlite:///./"):
    Path("api_store").mkdir(parents=True, exist_ok=True)

# SQLite + a threaded server needs check_same_thread off; harmless elsewhere.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency: a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  -- register mappers before create_all
    Base.metadata.create_all(bind=engine)
