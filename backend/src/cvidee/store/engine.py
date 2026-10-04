"""SQLite engine/session factory with WAL, busy_timeout and foreign keys (ADR-001)."""

import os
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from cvidee.config import get_settings

BUSY_TIMEOUT_MS = 5000


def database_url(path: Path | None = None) -> str:
    """SQLAlchemy URL: ``CVIDEE_DB_URL`` if set, else SQLite at ``CVIDEE_DB_PATH``."""
    if path is None:
        env = os.environ.get("CVIDEE_DB_URL")
        if env:
            return env
        path = get_settings().db_path
    return f"sqlite:///{path}"


def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    """Create an engine; for SQLite every new connection gets the required pragmas."""
    engine = create_engine(url, echo=echo)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
