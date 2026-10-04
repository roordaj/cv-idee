"""Stage 3 — operating modes (ADR-002 §3.3, FR-09). Pure: no I/O, no wall clock."""

from __future__ import annotations

from collections.abc import Sequence

from cvidee.analysis.types import (
    AnalysisWindow,
    DurationMs,
    Mode,
    ModeSegment,
    PipelineConfig,
    SignalTimeline,
)


def map_mode_code(code: str, mapping: Sequence[tuple[str, Mode]]) -> Mode | None:
    """Map a status/mode code to a mode; ``None`` for unmapped codes (→ ``UNKNOWN``)."""
    raise NotImplementedError


def classify_modes(
    timelines: Sequence[SignalTimeline],
    config: PipelineConfig,
    window: AnalysisWindow,
) -> tuple[ModeSegment, ...]:
    """Partition ``window.context`` into mode segments.

    * With an operating-mode signal: mode from :func:`map_mode_code`, certainty ``DIRECT``.
    * Without it: inferred from flame, heat demand, flow setpoint and pump state
      (certainty ``INFERRED``, "beperkte zekerheid").
    * ``AFTERRUN``: pump running / afterrun status after flame-off without demand, at most
      ``config.afterrun_max_ms``.
    * Any instant where the signals needed for a decision are unknown → ``UNKNOWN`` with
      certainty ``NONE``; unknown is never classified as standby.
    * Adjacent equal segments are merged, then split on the canonical grid
      (:func:`split_on_grid`).

    Returns:
        Contiguous segments covering ``window.context``, sorted by ``start``.
    """
    raise NotImplementedError


def split_on_grid(segments: Sequence[ModeSegment], grid_ms: DurationMs) -> tuple[ModeSegment, ...]:
    """Split segments at canonical UTC grid boundaries (ADR-002 §4.5) so that keys
    (``start``) do not depend on where a run's window started."""
    raise NotImplementedError
