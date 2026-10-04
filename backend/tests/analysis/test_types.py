"""Invariants of the analysis types (ADR-002)."""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cvidee.analysis.types import (
    HOUR_MS,
    MINUTE_MS,
    AnalysisWindow,
    BurnerCycle,
    EndReason,
    MetricName,
    MetricValue,
    MetricWindow,
    MetricWindowKind,
    Mode,
    ModeCertainty,
    ModeSegment,
    Observation,
    ObservationKind,
    PipelineConfig,
    Provenance,
    QualityEvent,
    QualityEventKind,
    Role,
    Scope,
    ScopeKind,
    SignalRef,
    SignalTimeline,
    TimeRange,
    UnknownInterval,
    UnknownReason,
    ValueInterval,
    ValueKind,
    floor_to_grid,
)

FLAME = SignalRef(Role.FLAME)
PROV = Provenance(ValueKind.REPORTED, "binary_sensor.flame")


def _value(start: int, end: int, value: bool = True) -> ValueInterval:
    return ValueInterval(start, end, value, PROV, start, ObservationKind.CHANGE)


class TestTimeRange:
    def test_rejects_empty_and_reversed(self) -> None:
        with pytest.raises(ValueError, match="end"):
            TimeRange(10, 10)
        with pytest.raises(ValueError, match="end"):
            TimeRange(10, 5)

    def test_intersect(self) -> None:
        assert TimeRange(0, 10).intersect(TimeRange(5, 20)) == TimeRange(5, 10)
        assert TimeRange(0, 10).intersect(TimeRange(10, 20)) is None

    def test_frozen(self) -> None:
        rng = TimeRange(0, 1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            rng.start = 5  # type: ignore[misc]


@given(st.integers(min_value=0, max_value=2**45), st.sampled_from([MINUTE_MS, HOUR_MS]))
def test_floor_to_grid(ts: int, grid: int) -> None:
    floored = floor_to_grid(ts, grid)
    assert floored <= ts < floored + grid
    assert floored % grid == 0


class TestIntervals:
    def test_value_interval_validation(self) -> None:
        with pytest.raises(ValueError, match="ValueInterval"):
            _value(5, 5)
        with pytest.raises(ValueError, match="observed_at"):
            ValueInterval(0, 10, 1.0, PROV, 10, ObservationKind.POLL)

    def test_clipped_value_interval_keeps_older_evidence(self) -> None:
        interval = ValueInterval(100, 200, 1.0, PROV, 50, ObservationKind.CHANGE)
        assert interval.observed_at < interval.start

    def test_unknown_interval_validation(self) -> None:
        with pytest.raises(ValueError, match="UnknownInterval"):
            UnknownInterval(5, 1, UnknownReason.STALE)


class TestSignalTimeline:
    def _timeline(self) -> SignalTimeline:
        return SignalTimeline(
            FLAME,
            TimeRange(0, 100),
            (
                _value(0, 30, False),
                UnknownInterval(30, 60, UnknownReason.DISCONNECTED),
                _value(60, 100, True),
            ),
        )

    def test_must_cover_span(self) -> None:
        with pytest.raises(ValueError, match="gap or overlap"):
            SignalTimeline(FLAME, TimeRange(0, 100), (_value(0, 30), _value(40, 100)))
        with pytest.raises(ValueError, match="gap or overlap"):
            SignalTimeline(FLAME, TimeRange(0, 100), (_value(0, 50), _value(40, 100)))
        with pytest.raises(ValueError, match="span ends later"):
            SignalTimeline(FLAME, TimeRange(0, 100), (_value(0, 50),))
        with pytest.raises(ValueError, match="no intervals"):
            SignalTimeline(FLAME, TimeRange(0, 100), ())

    def test_lookup(self) -> None:
        tl = self._timeline()
        assert tl.value_at(0) is False
        assert tl.value_at(29) is False
        assert tl.value_at(30) is None  # unknown, not "off"
        assert tl.value_at(60) is True
        assert tl.value_at(100) is None  # outside span
        assert isinstance(tl.at(45), UnknownInterval)

    def test_unknown_time_is_not_counted_as_known(self) -> None:
        tl = self._timeline()
        assert tl.known_ms(TimeRange(0, 100)) == 70
        assert tl.coverage(TimeRange(20, 70)) == pytest.approx(20 / 50)
        assert tl.coverage(TimeRange(100, 200)) == 0.0
        assert len(tl.values) == 2
        assert len(tl.unknowns) == 1


class TestSignals:
    def test_scope_validation(self) -> None:
        with pytest.raises(ValueError, match="requires a key"):
            Scope(ScopeKind.ROOM)
        with pytest.raises(ValueError, match="singleton"):
            Scope(ScopeKind.BOILER, "x")

    def test_role_scope(self) -> None:
        room = Scope(ScopeKind.ROOM, "slaapkamer")
        assert str(SignalRef(Role.ROOM_TEMPERATURE, room)) == "room_temperature@room:slaapkamer"
        assert str(FLAME) == "flame@boiler"
        with pytest.raises(ValueError, match="cannot have scope"):
            SignalRef(Role.ROOM_TEMPERATURE)
        with pytest.raises(ValueError, match="cannot have scope"):
            SignalRef(Role.FLAME, room)
        circuit = Scope(ScopeKind.CIRCUIT, "boven")
        assert SignalRef(Role.FLOW_TEMPERATURE, circuit).scope == circuit

    def test_derived_provenance_inherits_weakest(self) -> None:
        measured = Provenance(ValueKind.MEASURED, "sensor.flow")
        estimated = Provenance(ValueKind.ESTIMATED, "sensor.x")
        assert Provenance.derive("d", measured, PROV).kind is ValueKind.DERIVED
        assert Provenance.derive("d", measured, estimated).kind is ValueKind.ESTIMATED

    def test_observation(self) -> None:
        obs = Observation(FLAME, 10, True, ObservationKind.CHANGE, last_reported=20)
        assert obs.evidence_ts == 20
        with pytest.raises(ValueError, match="last_reported"):
            Observation(FLAME, 10, True, ObservationKind.CHANGE, last_reported=5)


class TestAnalysisWindow:
    def test_for_run(self) -> None:
        now = 10 * HOUR_MS + 17 * MINUTE_MS
        window = AnalysisWindow.for_run(
            watermark=9 * HOUR_MS + 30 * MINUTE_MS,
            now=now,
            lookback_ms=6 * HOUR_MS,
            settle_ms=2 * MINUTE_MS,
            grid_ms=HOUR_MS,
        )
        assert window.end == now - 2 * MINUTE_MS
        assert window.emit_from == 9 * HOUR_MS
        assert window.context_start == 3 * HOUR_MS
        assert window.emits(9 * HOUR_MS)
        assert not window.emits(window.end)
        assert not window.emits(8 * HOUR_MS)

    def test_ordering(self) -> None:
        with pytest.raises(ValueError, match="context_start <= emit_from <= end"):
            AnalysisWindow(context_start=10, emit_from=5, end=20)


class TestBurnerCycle:
    def test_complete_cycle(self) -> None:
        c = BurnerCycle(0, 180_000, 180_000, True, True, Mode.CH, EndReason.STOP_DURING_DEMAND)
        assert c.counts_as_start
        with pytest.raises(ValueError, match="end - start"):
            BurnerCycle(0, 180_000, 1, True, True, Mode.CH, EndReason.STOP_DURING_DEMAND)

    def test_open_cycle_is_provisional(self) -> None:
        BurnerCycle(0, None, 60_000, False, True, Mode.CH, None)
        with pytest.raises(ValueError, match="open cycle"):
            BurnerCycle(0, None, 60_000, False, True, Mode.CH, None, final=True)
        with pytest.raises(ValueError, match="open cycle"):
            BurnerCycle(0, None, 60_000, False, True, Mode.CH, EndReason.DEMAND_ENDED)

    def test_data_gap_cycle_is_incomplete(self) -> None:
        BurnerCycle(0, 300_000, 300_000, False, True, Mode.CH, EndReason.DATA_GAP)
        with pytest.raises(ValueError, match="complete requires"):
            BurnerCycle(0, 300_000, 300_000, True, True, Mode.CH, EndReason.DATA_GAP)

    def test_unobserved_start_never_counts(self) -> None:
        c = BurnerCycle(0, 300_000, 300_000, False, False, Mode.CH, EndReason.DEMAND_ENDED)
        assert not c.counts_as_start
        with pytest.raises(ValueError, match="complete requires"):
            BurnerCycle(0, 300_000, 300_000, True, False, Mode.CH, EndReason.DEMAND_ENDED)

    def test_closed_cycle_needs_reason(self) -> None:
        with pytest.raises(ValueError, match="end reason"):
            BurnerCycle(0, 300_000, 300_000, False, True, Mode.CH, None)


class TestOtherTypes:
    def test_mode_segment_unknown_iff_no_certainty(self) -> None:
        ModeSegment(0, 10, Mode.UNKNOWN, ModeCertainty.NONE)
        with pytest.raises(ValueError, match="UNKNOWN iff"):
            ModeSegment(0, 10, Mode.UNKNOWN, ModeCertainty.INFERRED)
        with pytest.raises(ValueError, match="UNKNOWN iff"):
            ModeSegment(0, 10, Mode.CH, ModeCertainty.NONE)

    def test_metric_value(self) -> None:
        window = MetricWindow(MetricWindowKind.HOUR, TimeRange(0, HOUR_MS))
        MetricValue(MetricName.STARTS, window, 4.0, "count", 1800.0, 0.5)
        with pytest.raises(ValueError, match="coverage"):
            MetricValue(MetricName.STARTS, window, 4.0, "count", 1800.0, 1.5)
        with pytest.raises(ValueError, match="exceeds window"):
            MetricValue(MetricName.STARTS, window, 4.0, "count", 3601.0, 1.0)
        with pytest.raises(ValueError, match="cycle_start"):
            MetricWindow(MetricWindowKind.CYCLE, TimeRange(0, 10))

    def test_quality_event(self) -> None:
        QualityEvent(QualityEventKind.CONNECTION_LOST, None, 0, None)
        with pytest.raises(ValueError, match="ongoing"):
            QualityEvent(QualityEventKind.CONNECTION_LOST, None, 0, None, final=True)

    def test_pipeline_config_defaults_and_lookback(self) -> None:
        cfg = PipelineConfig(signals=())
        assert cfg.lookback_ms == 6 * HOUR_MS
        assert cfg.settle_ms == 2 * MINUTE_MS
        with pytest.raises(ValueError, match="lookback_ms"):
            PipelineConfig(signals=(), lookback_ms=HOUR_MS)
        with pytest.raises(ValueError, match="lookahead"):
            PipelineConfig(signals=(), end_reason_lookahead_ms=5 * MINUTE_MS)
