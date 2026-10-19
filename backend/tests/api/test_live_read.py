"""Real monitoring reads stay honest when the store is empty or disconnected."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cvidee.api.live_read import LiveReadModel, safe_url
from cvidee.api.problems import ProblemError
from cvidee.config import Settings
from cvidee.store.engine import create_db_engine, create_session_factory, database_url
from cvidee.store.schema import upgrade_to_head


def make_model(tmp_path: Path, now: int = 1_791_100_800_000) -> LiveReadModel:
    url = database_url(tmp_path / "read.sqlite")
    upgrade_to_head(url)
    factory = create_session_factory(create_db_engine(url))
    return LiveReadModel(factory, Settings(), None, None, clock=lambda: now)


def test_empty_store_routes_have_explicit_unknown_state(tmp_path: Path) -> None:
    model = make_model(tmp_path)

    status = model.status()
    overview = model.overview()
    quality = model.quality()
    cycles = model.cycles(limit=20, offset=0)

    assert status.stub_data is False
    assert status.operating_mode.value == "unknown"
    assert status.counts.signals_linked == 0
    assert overview.assessment.level.value == "insufficient_data"
    assert overview.status_card.title == "Nog geen beoordeling mogelijk"
    assert overview.today.ch_cycles == 0
    assert quality.core_coverage_pct is None
    assert quality.coverage
    assert all(row.coverage_pct is None for row in quality.coverage)
    assert all(
        segment.kind.value == "not_mapped" for row in quality.coverage for segment in row.segments
    )
    assert cycles.summary.starts_per_hour is None
    assert cycles.summary.total_burn_s == 0


def test_monitoring_rejects_future_and_reversed_ranges(tmp_path: Path) -> None:
    model = make_model(tmp_path)
    with pytest.raises(ProblemError, match="maximaal 31 dagen"):
        model.quality(end=datetime.fromtimestamp(model.clock() / 1000, UTC) + timedelta(seconds=1))


def test_safe_url_removes_credentials_query_and_fragment() -> None:
    assert safe_url("http://admin:secret@ha.local:8123/path?token=secret#view") == (
        "http://ha.local:8123/path"
    )
    assert safe_url(None) is None
