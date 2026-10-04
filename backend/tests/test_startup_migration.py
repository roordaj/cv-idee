"""App startup migrates the database (#73)."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from cvidee.config import Settings
from cvidee.main import create_app
from cvidee.store.models import Base


def _settings(db_path: Path) -> Settings:
    return Settings.model_validate({"CVIDEE_DB_PATH": str(db_path)})


def test_lifespan_creates_directory_and_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "data" / "cvidee.sqlite"
    with TestClient(create_app(_settings(db_path))) as client:
        assert client.get("/api/health").status_code == 200
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_restart_is_idempotent_and_keeps_data(tmp_path: Path) -> None:
    db_path = tmp_path / "cvidee.sqlite"
    app = create_app(_settings(db_path))
    with TestClient(app):
        pass
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO connection_events (source, ts, up) VALUES ('ws', 1, 1)"))
    with TestClient(app):
        pass
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM connection_events")).scalar() == 1
    engine.dispose()
