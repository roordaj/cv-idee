"""FR-06 / ADR-002 §6: processing in chunks yields the same result as processing at once.

The runner is simulated here with the exact replace-from semantics of ADR-002 §4: each run
deletes derived items with key ``>= window.emit_from`` and inserts the run's output. Stage 5
(metrics) contributes nothing until #28/#29 register their functions in
``cvidee.analysis.pipeline.METRIC_STAGES``; the runner-level variant over a real database is
``tests/runner/test_runner.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cvidee.analysis.pipeline import run_pipeline
from cvidee.analysis.types import (
    MINUTE_MS,
    AnalysisWindow,
    BurnerCycle,
    ConnectionEvent,
    ConnectionSource,
    MetricValue,
    ModeSegment,
    Observation,
    ObservationKind,
    PipelineConfig,
    Provenance,
    QualityEvent,
    Role,
    SignalConfig,
    SignalRef,
    TimestampMs,
    ValueKind,
)

T0: TimestampMs = 1_790_000_000_000 - (1_790_000_000_000 % (60 * MINUTE_MS))
"""A whole UTC hour in late Sept 2026."""

FLAME = SignalRef(Role.FLAME)
DEMAND = SignalRef(Role.HEAT_DEMAND)

CONFIG = PipelineConfig(
    signals=(
        SignalConfig(FLAME, Provenance(ValueKind.REPORTED, "binary_sensor.flame")),
        SignalConfig(DEMAND, Provenance(ValueKind.REPORTED, "binary_sensor.heat_demand")),
    ),
    config_hash="test",
)


@dataclass
class Store:
    """In-memory stand-in for the derived tables, keyed like the real ones."""

    cycles: dict[TimestampMs, BurnerCycle] = field(default_factory=dict)
    modes: dict[TimestampMs, ModeSegment] = field(default_factory=dict)
    quality: dict[tuple[str, str, str, str, TimestampMs], QualityEvent] = field(
        default_factory=dict
    )
    metrics: dict[tuple[str, str, str, TimestampMs, TimestampMs | None], MetricValue] = field(
        default_factory=dict
    )

    def replace_from(self, emit_from: TimestampMs) -> None:
        self.cycles = {k: v for k, v in self.cycles.items() if k < emit_from}
        self.modes = {k: v for k, v in self.modes.items() if k < emit_from}
        self.quality = {k: v for k, v in self.quality.items() if k[4] < emit_from}
        self.metrics = {k: v for k, v in self.metrics.items() if k[3] < emit_from}

    def upsert(
        self,
        cycles: Sequence[BurnerCycle],
        modes: Sequence[ModeSegment],
        quality: Sequence[QualityEvent],
        metrics: Sequence[MetricValue],
    ) -> None:
        for c in cycles:
            self.cycles[c.key] = c
        for m in modes:
            self.modes[m.start] = m
        for q in quality:
            self.quality[q.key] = q
        for mv in metrics:
            key = (
                mv.name.value,
                "" if mv.mode is None else mv.mode.value,
                mv.window.kind.value,
                mv.window.range.start,
                mv.window.cycle_start,
            )
            self.metrics[key] = mv


def _select(
    items: Sequence[Observation], context_start: TimestampMs, end: TimestampMs
) -> list[Observation]:
    """What the runner reads: items in ``[context_start, end)`` + carry-in per signal."""
    selected = [o for o in items if context_start <= o.ts < end]
    for signal in {o.signal for o in items}:
        before = [o for o in items if o.signal == signal and o.ts < context_start]
        if before:
            selected.append(max(before, key=lambda o: o.sort_key))
    return selected


def _select_events(
    events: Sequence[ConnectionEvent], context_start: TimestampMs, end: TimestampMs
) -> list[ConnectionEvent]:
    selected = [e for e in events if context_start <= e.ts < end]
    before = [e for e in events if e.ts < context_start]
    if before:
        selected.append(max(before, key=lambda e: (e.ts, e.source.value, e.up)))
    return selected


def run_chunked(
    observations: Sequence[Observation],
    events: Sequence[ConnectionEvent],
    horizons: Sequence[TimestampMs],
    config: PipelineConfig,
) -> Store:
    """Simulate the runner (ADR-002 §4) for a sequence of increasing horizons."""
    store = Store()
    watermark = T0
    for horizon in horizons:
        now = horizon + config.settle_ms
        window = AnalysisWindow.for_run(
            watermark=watermark,
            now=now,
            lookback_ms=config.lookback_ms,
            settle_ms=config.settle_ms,
            grid_ms=config.grid_ms,
        )
        result = run_pipeline(
            _select(observations, window.context_start, window.end),
            _select_events(events, window.context_start, window.end),
            config,
            window,
            now,
        )
        store.replace_from(window.emit_from)
        store.upsert(result.cycles, result.mode_segments, result.quality_events, result.metrics)
        watermark = result.next_watermark
    return store


@st.composite
def histories(
    draw: st.DrawFn,
) -> tuple[list[Observation], list[ConnectionEvent], list[TimestampMs]]:
    """Random flame/demand histories with connection outages and random chunk horizons."""
    observations: list[Observation] = [
        Observation(FLAME, T0, False, ObservationKind.POLL),
        Observation(DEMAND, T0, False, ObservationKind.POLL),
    ]
    events: list[ConnectionEvent] = [ConnectionEvent(T0, ConnectionSource.WS, up=True)]
    t, flame, demand, connected = T0, False, False, True
    for _ in range(draw(st.integers(min_value=1, max_value=60))):
        t += draw(st.integers(min_value=1, max_value=40)) * MINUTE_MS // 2
        action = draw(st.sampled_from(["flame", "flame", "demand", "outage"]))
        if action == "flame":
            flame = not flame
            observations.append(Observation(FLAME, t, flame, ObservationKind.CHANGE))
        elif action == "demand":
            demand = not demand
            observations.append(Observation(DEMAND, t, demand, ObservationKind.CHANGE))
        else:
            connected = not connected
            events.append(ConnectionEvent(t, ConnectionSource.WS, up=connected))
            if connected:  # reconnect: get_states yields polls, never transitions
                observations.append(Observation(FLAME, t, flame, ObservationKind.POLL))
                observations.append(Observation(DEMAND, t, demand, ObservationKind.POLL))
    end = t + draw(st.integers(min_value=1, max_value=120)) * MINUTE_MS
    cuts = draw(st.lists(st.integers(min_value=T0 + 1, max_value=end - 1), max_size=12))
    horizons = [*sorted(set(cuts)), end]
    return observations, events, horizons


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(histories())
def test_chunked_equals_whole(
    history: tuple[list[Observation], list[ConnectionEvent], list[TimestampMs]],
) -> None:
    observations, events, horizons = history
    whole = run_chunked(observations, events, horizons[-1:], CONFIG)
    chunked = run_chunked(observations, events, horizons, CONFIG)
    assert chunked.cycles == whole.cycles
    assert chunked.modes == whole.modes
    assert chunked.quality == whole.quality
    assert chunked.metrics == whole.metrics


def test_reconnect_poll_is_not_a_start() -> None:
    """Scenario 5 / FR-08: flame on seen first via a poll after an outage is no new start."""
    observations = [
        Observation(FLAME, T0, False, ObservationKind.POLL),
        Observation(FLAME, T0 + 10 * MINUTE_MS, True, ObservationKind.CHANGE),
        Observation(FLAME, T0 + 50 * MINUTE_MS, True, ObservationKind.POLL),
        Observation(FLAME, T0 + 55 * MINUTE_MS, False, ObservationKind.CHANGE),
    ]
    events = [
        ConnectionEvent(T0, ConnectionSource.WS, up=True),
        ConnectionEvent(T0 + 20 * MINUTE_MS, ConnectionSource.WS, up=False),
        ConnectionEvent(T0 + 50 * MINUTE_MS, ConnectionSource.WS, up=True),
    ]
    store = run_chunked(observations, events, [T0 + 2 * 60 * MINUTE_MS], CONFIG)
    cycles = sorted(store.cycles.values(), key=lambda c: c.start)
    assert [c.counts_as_start for c in cycles] == [True, False]
    assert cycles[0].end == T0 + 20 * MINUTE_MS
    assert not cycles[0].complete
