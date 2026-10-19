"""Source-bound AM012 interpretation, validity and real recorder replay (#123)."""

import asyncio
import json
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from cvidee.analysis.modes import classify_modes
from cvidee.analysis.timeline import build_timelines
from cvidee.analysis.types import (
    AnalysisWindow,
    Mode,
    ModeCertainty,
    ObservationKind,
    Role,
    SignalRef,
)
from cvidee.api.problems import ProblemError
from cvidee.api.schemas.signals import SignalMappingUpdate
from cvidee.ingest.ha_client import HAState
from cvidee.runner.service import AnalysisRunner, RunnerSettings
from cvidee.runner.sources import (
    SourceSettings,
    build_pipeline_config,
    load_mapped_signals,
    load_window_input,
    mode_mapping_snapshot,
)
from cvidee.signals.backend import SignalsBackend
from cvidee.store.derived import SqlDerivedDataRepository
from cvidee.store.enums import ObservationOrigin, RunStatus
from cvidee.store.models import AnalysisRun, SignalMapping
from cvidee.store.observations import SqlObservationRepository
from cvidee.store.records import ObservationRecord

from .test_backend import NOW
from .test_backend import backend as backend
from .test_backend import sessions as sessions

TABLE: dict[str, float | str | bool | None] = {
    "0": "standby",
    "1": "unknown",
    "2": "unknown",
    "3": "ch",
    "4": "dhw",
    "5": "unknown",
    "6": "afterrun",
    "8": "unknown",
}
MEANING = (
    "AM012, gatewayomschrijving gekoppeld aan recordercode; handleiding 7685807 v11 tabel 72. "
    "Lokale decoder niet onafhankelijk gevalideerd."
)
MODE = SignalRef(Role.OPERATING_MODE)


async def configured(backend: SignalsBackend) -> None:
    await backend.update_signal(
        "operating_mode@boiler",
        SignalMappingUpdate(
            entity_id="sensor.mode",
            value_map=TABLE,
            meaning=MEANING,
        ),
    )


def record(
    state: str, ts: int, origin: ObservationOrigin = ObservationOrigin.LIVE
) -> ObservationRecord:
    try:
        numeric = float(state)
    except ValueError:
        numeric = None
    return ObservationRecord("sensor.mode", ts, state, numeric, ObservationKind.CHANGE, origin, ts)


async def test_mapping_is_explicit_and_requires_provenance(backend: SignalsBackend) -> None:
    for body in (
        SignalMappingUpdate(entity_id="sensor.mode", value_map=TABLE),
        SignalMappingUpdate(entity_id="sensor.mode", value_map={"3": True}, meaning=MEANING),
        SignalMappingUpdate(
            entity_id="sensor.mode", value_map={"3": "CV-bedrijf"}, meaning=MEANING
        ),
    ):
        with pytest.raises(ProblemError) as exc:
            await backend.update_signal("operating_mode@boiler", body)
        assert exc.value.problem.status == 422
    await configured(backend)
    signal = next(s for s in backend.signal_list().items if s.role is Role.OPERATING_MODE)
    assert signal.value_map == TABLE
    assert signal.mapping_version is not None
    assert signal.meaning == MEANING


async def test_source_replacement_does_not_inherit_mode_semantics(backend: SignalsBackend) -> None:
    await configured(backend)
    assert backend.client is not None
    cast(AsyncMock, backend.client.get_states).return_value = [HAState("sensor.other_mode", "3")]
    backend.clock = lambda: NOW + 1000
    signal = await backend.update_signal(
        "operating_mode@boiler", SignalMappingUpdate(entity_id="sensor.other_mode")
    )
    assert signal.value_map is None
    assert signal.meaning is None
    with backend.sessions() as session:
        versions = list(session.scalars(select(SignalMapping).order_by(SignalMapping.id)))
        assert versions[0].value_map == TABLE
        assert versions[0].meaning == MEANING
        assert versions[0].valid_to_ts == NOW + 1000


async def test_revision_boundaries_and_hash_keep_historical_table(backend: SignalsBackend) -> None:
    await configured(backend)
    with backend.sessions() as session:
        mapped = load_mapped_signals(session)
        config = build_pipeline_config(session, mapped, SourceSettings())
        snapshot = mode_mapping_snapshot(mapped)
    backend.clock = lambda: NOW + 1000
    await backend.update_signal(
        "operating_mode@boiler",
        SignalMappingUpdate(
            entity_id="sensor.mode",
            value_map={"3": "dhw"},
            meaning="Nieuwe expliciete testbronversie",
        ),
    )
    with backend.sessions.begin() as session:
        SqlObservationRepository(session).add_observations(
            [record("3", NOW + 100), record("3.0", NOW + 1100)]
        )
        mapped = load_mapped_signals(session)
        changed = build_pipeline_config(session, mapped, SourceSettings())
        assert config.config_hash != changed.config_hash
        assert snapshot[0]["value_map"] == TABLE
        window = AnalysisWindow(NOW, NOW, NOW + 2000)
        observations, events = load_window_input(session, mapped, SourceSettings(), window)
        segments = classify_modes(
            build_timelines(observations, events, changed, window), changed, window
        )
        assert any(s.mode is Mode.CH and s.end <= NOW + 1000 for s in segments)
        assert any(s.mode is Mode.DHW and s.start >= NOW + 1100 for s in segments)
        assert mode_mapping_snapshot(mapped)[0]["meaning"] == MEANING


@pytest.mark.parametrize("raw", ["1", "2", "5", "8", "9", "10", "99", "3.5", "unavailable"])
async def test_transitional_unvalidated_and_invalid_codes_stay_unknown(
    backend: SignalsBackend, raw: str
) -> None:
    await configured(backend)
    with backend.sessions.begin() as session:
        SqlObservationRepository(session).add_observations([record(raw, NOW + 100)])
        mapped = load_mapped_signals(session)
        config = build_pipeline_config(session, mapped, SourceSettings())
        window = AnalysisWindow(NOW + 100, NOW + 100, NOW + 1000)
        observations, events = load_window_input(session, mapped, SourceSettings(), window)
        modes = classify_modes(
            build_timelines(observations, events, config, window), config, window
        )
        assert all(s.mode is Mode.UNKNOWN and s.certainty is ModeCertainty.NONE for s in modes)


def _recording_rows() -> list[dict[str, object]]:
    path = (
        Path(__file__).resolve().parents[3]
        / "fixtures/recordings/calenta-can-48h/observations.jsonl"
    )
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_real_recording_has_identical_live_and_import_modes_without_invented_flame(
    backend: SignalsBackend,
) -> None:
    await configured(backend)
    data = await asyncio.to_thread(_recording_rows)
    records = [
        record(str(row["state"]), NOW + int(str(row["t_us"])) // 1000)
        for row in data
        if row["entity"] == "sensor.gateway_mqtt_ketelstatus_am012"
    ]
    end = NOW + 48 * 60 * 60 * 1000
    with backend.sessions.begin() as session:
        SqlObservationRepository(session).add_observations(records)
    # Deliberately no synthetic flame or demand mapping: AM012 status is not flame evidence.
    runner = AnalysisRunner(backend.sessions, RunnerSettings(chunk_ms=end - NOW))
    runner.run_range(NOW, end)
    with backend.sessions() as session:
        repo = SqlDerivedDataRepository(session)
        imported = repo.mode_segments(NOW, end)
        assert {s.mode for s in imported} == {
            Mode.CH,
            Mode.DHW,
            Mode.AFTERRUN,
            Mode.STANDBY,
            Mode.UNKNOWN,
        }
        assert repo.burner_cycles(NOW, end) == []
        runs = list(
            session.scalars(select(AnalysisRun).where(AnalysisRun.status == RunStatus.SUCCEEDED))
        )
        assert runs
        assert all(run.stats["operating_mode_mappings"][0]["value_map"] == TABLE for run in runs)
    runner.request_recompute(NOW, end, reason="live-equivalence")
    runner.tick(end + 120_000)
    with backend.sessions() as session:
        live = SqlDerivedDataRepository(session).mode_segments(NOW, end)
        assert [(s.start, s.end, s.mode, s.certainty) for s in live] == [
            (s.start, s.end, s.mode, s.certainty) for s in imported
        ]


async def test_unmapped_raw_mode_names_are_not_a_hidden_default(backend: SignalsBackend) -> None:
    await backend.update_signal(
        "operating_mode@boiler", SignalMappingUpdate(entity_id="sensor.mode")
    )
    with backend.sessions.begin() as session:
        SqlObservationRepository(session).add_observations([record("ch", NOW + 1)])
        mapped = load_mapped_signals(session)
        config = build_pipeline_config(session, mapped, SourceSettings())
        assert config.mode_mapping == ()
        window = AnalysisWindow(NOW + 1, NOW + 1, NOW + 1000)
        observations, events = load_window_input(session, mapped, SourceSettings(), window)
        modes = classify_modes(
            build_timelines(observations, events, config, window), config, window
        )
        assert all(s.mode is Mode.UNKNOWN for s in modes)


def test_advice_snapshots_preserve_the_explicit_synthetic_table(tmp_path: Path) -> None:
    from cvidee.store.models import RecommendationSnapshot

    from ..changes.test_evaluation_integration import seed_evaluation

    factory, runner, data = seed_evaluation(tmp_path, "07-aanvoerwijziging-comfort")
    runner.tick(data.end_ms + data.config.settle_ms)
    with factory() as session:
        snapshots = list(session.scalars(select(RecommendationSnapshot)))
        assert snapshots
        assert all(
            row.settings["pipeline_mode_mapping"] == dict(data.config.mode_mapping)
            for row in snapshots
        )
        assert all(row.settings["operating_mode_mappings"] for row in snapshots)


async def test_legacy_table_without_provenance_does_not_count_as_known_mode(
    backend: SignalsBackend,
) -> None:
    await configured(backend)
    with backend.sessions.begin() as session:
        row = session.scalar(select(SignalMapping))
        assert row is not None
        row.meaning = None  # emulate a pre-validation database mapping
        SqlObservationRepository(session).add_observations([record("3", NOW + 1)])
        session.flush()
        mapped = load_mapped_signals(session)
        config = build_pipeline_config(session, mapped, SourceSettings())
        window = AnalysisWindow(NOW, NOW, NOW + 1000)
        observations, events = load_window_input(session, mapped, SourceSettings(), window, config)
        timelines = build_timelines(observations, events, config, window)
        assert timelines
        assert all(not timeline.values for timeline in timelines)
        assert not mode_mapping_snapshot(mapped)[0]["source_semantics_confirmed"]
