"""
db.py — Phase 0

SQLAlchemy engine + session management. Everything else (models.py,
services/*) imports Base and get_db from here — nobody creates their own
engine, or Phase 1's normalization writes and Phase 5's search reads could
end up on different connections/transactions.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_URL


class Base(DeclarativeBase):
    """Declarative base shared by every model in models.py."""


# check_same_thread=False is only needed for sqlite (dashboard + cli both
# touching the same file); harmless no-op for other backends via connect_args
# filtering below.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (no-op on existing tables).

    Import models here (not at module top) so models.py's import of Base
    from this module doesn't create a circular import.
    """
    import models  # noqa: F401  (ensures all model classes are registered)

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI/Streamlit-style dependency: yields a session, guarantees close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context-manager form for scripts (seed_demo.py, cli.py) that aren't
    running inside a request/dependency-injection framework.

    Commits on clean exit, rolls back on exception, always closes.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reset_db() -> None:
    """Drop and recreate all tables. DEMO/TEST USE ONLY — destructive.

    Deliberately not wired to any UI button; only callable from scripts
    (e.g. seed_demo.py) so a stray click can't wipe the database.
    """
    import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
