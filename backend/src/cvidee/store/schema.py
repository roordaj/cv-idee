"""Programmatic access to the Alembic migrations in ``backend/migrations``.

In a source checkout the migrations are found next to the package (``backend/``). A
deployment that installs the package non-editable must ship ``alembic.ini`` and
``migrations/`` and point ``CVIDEE_MIGRATIONS_DIR`` at the directory containing both.
"""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def backend_dir() -> Path:
    """Directory holding ``alembic.ini`` and ``migrations/``."""
    env = os.environ.get("CVIDEE_MIGRATIONS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def alembic_config(db_url: str) -> Config:
    """Alembic config for ``db_url`` that does not reconfigure application logging."""
    base = backend_dir()
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


def upgrade_to_head(db_url: str) -> None:
    """Bring the database at ``db_url`` to the latest schema revision."""
    command.upgrade(alembic_config(db_url), "head")
