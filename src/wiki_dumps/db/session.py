"""Database engine factory and session context manager."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from wiki_dumps.db.base import Base


@event.listens_for(Engine, "connect")
def _set_sqlite_wal(dbapi_connection: object, _: object) -> None:  # pyright: ignore[reportUnusedFunction]
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute("PRAGMA synchronous=NORMAL")
        dbapi_connection.execute("PRAGMA busy_timeout=30000")


def make_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine for the given database URL.

    SQLite connections are configured for thread-safety (check_same_thread=False)
    to allow use from Dask worker threads.
    """
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, echo=echo, connect_args=connect_args)


def create_all_tables(engine: Engine) -> None:
    """Create all tables defined in Base metadata (non-migration path)."""
    Base.metadata.create_all(engine)


@contextmanager
def get_session(engine: Engine, *, expire_on_commit: bool = True) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session, committing on success or rolling back on error."""
    with Session(engine, expire_on_commit=expire_on_commit) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
