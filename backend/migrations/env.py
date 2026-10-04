"""Alembic environment for CV-idee (ADR-001).

URL resolution order: ``config.attributes["connection"]`` (tests pass an open
connection), ``sqlalchemy.url`` main option, ``-x db_url=…``, ``CVIDEE_DB_URL``.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from cvidee.store.engine import create_db_engine, database_url
from cvidee.store.models import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    x_url = context.get_x_argument(as_dictionary=True).get("db_url")
    return x_url or database_url()


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite ALTER support
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    engine = create_db_engine(_url())
    with engine.connect() as conn:
        _configure(conn)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
