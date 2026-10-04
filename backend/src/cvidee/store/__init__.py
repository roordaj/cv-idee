"""Persistence layer.

SQLite (WAL mode) with SQLAlchemy 2 and Alembic migrations, behind a repository
interface so another backend (e.g. TimescaleDB) can be added later. All timestamps are
stored in UTC; conversion to Europe/Amsterdam happens only for display.
"""
