"""Rule contract: protocol, context, finding candidates and parameters (ADR-004).

Conventions (see ``docs/adr/004-regels.md``):

* Rules are pure: :meth:`Rule.evaluate` reads only the :class:`RuleContext` and its
  parameters. No I/O, no wall clock (``ctx.now`` is a parameter), no SQLAlchemy.
* Observation, interpretation and advice are separate fields (FR-21).
* Certainty is a documented category (:class:`Certainty`), never a percentage (FR-22).
* Rule ids are the UI-facing kebab-case ids from design v3 (``kort-branden``); versions are
  semantic versions (FR-41).
* Parameters are pydantic models whose JSON schema drives the settings UI
  (``x-unit``/``x-step``/``x-group``/``x-rule``, design additions §1.5).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, ClassVar, Protocol, cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from cvidee.analysis.change_evaluation import EvaluationFact
from cvidee.analysis.room_comfort import RoomComfortMetrics
from cvidee.analysis.types import (
    BOILER,
    OUTDOOR,
    BurnerCycle,
    DurationMs,
    MetricName,
    MetricValue,
    Mode,
    ModeSegment,
    QualityEvent,
    QualityEventKind,
    Role,
    Scope,
    ScopeKind,
    SignalRef,
    SignalTimeline,
    TimeRange,
    TimestampMs,
)

RULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
LOCAL_TZ = "Europe/Amsterdam"


# --------------------------------------------------------------------------------------
# Classification enums
# --------------------------------------------------------------------------------------


class Category(StrEnum):
    """Finding category (design v3 ``cat``; the UI maps these to Dutch labels)."""

    CYCLES = "cycles"
    """Cycli."""
    TEMPERATURE = "temperature"
    """Temperatuur."""
    DATA_QUALITY = "data_quality"
    """Gegevenskwaliteit."""
    OPERATING_CONTEXT = "operating_context"
    """Bedrijfscontext."""
    HYDRAULIC = "hydraulic"
    """Hydraulisch."""
    COMFORT = "comfort"
    """Comfort."""
    ZONES = "zones"
    """Zones."""
    CONSUMPTION = "consumption"
    """Verbruik."""
    EFFECT_MEASUREMENT = "effect_measurement"
    """Effectmeting."""


class Severity(StrEnum):
    """Ernst: hoog / middel / laag / info."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Relevance(StrEnum):
    """Relevantie of a finding (requirements §5)."""

    ENERGY = "energy"
    COMFORT = "comfort"
    OPERATIONAL_STABILITY = "operational_stability"
    DATA_RELIABILITY = "data_reliability"
    """Betrouwbaarheid analyses (design v3, B-015)."""


class Certainty(StrEnum):
    """Zekerheid as an ordered, documented category (FR-22, FR-28; ADR-004 §5).

    Order (weak → strong): ``INSUFFICIENT_EVIDENCE`` < ``PRELIMINARY`` < ``MODERATE`` <
    ``REASONABLE`` < ``HIGH`` < ``HIGH_MEASURED``.
    """

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    """Onvoldoende bewijs: hard minimum not met; propose a measurement, no diagnosis."""
    PRELIMINARY = "preliminary"
    """Voorlopig: minimum met, but the pattern is not (yet) repeated over enough days."""
    MODERATE = "moderate"
    """Matig."""
    REASONABLE = "reasonable"
    """Redelijk."""
    HIGH = "high"
    """Hoog."""
    HIGH_MEASURED = "high_measured"
    """Hoog (gemeten): a direct measurement without an interpretation step."""

    @property
    def rank(self) -> int:
        return _CERTAINTY_ORDER.index(self)

    def lowered(self, steps: int = 1, *, floor: Certainty | None = None) -> Certainty:
        """This category ``steps`` steps weaker, but not below ``floor`` (if given)."""
        rank = max(self.rank - steps, 0 if floor is None else floor.rank)
        return _CERTAINTY_ORDER[min(rank, self.rank)]

    def at_most(self, cap: Certainty) -> Certainty:
        return self if self.rank <= cap.rank else cap


_CERTAINTY_ORDER: tuple[Certainty, ...] = (
    Certainty.INSUFFICIENT_EVIDENCE,
    Certainty.PRELIMINARY,
    Certainty.MODERATE,
    Certainty.REASONABLE,
    Certainty.HIGH,
    Certainty.HIGH_MEASURED,
)


# --------------------------------------------------------------------------------------
# Installation profile as seen by rules (mapped from the store by #20)
# --------------------------------------------------------------------------------------


class CircuitKind(StrEnum):
    DIRECT = "direct"
    """Radiators directly on the boiler circuit."""
    MIXING_MANIFOLD = "mixing_manifold"
    """Underfloor heating behind a mixing manifold: boiler ΔT is not the loop ΔT."""


@dataclass(frozen=True, slots=True)
class CircuitFacts:
    key: str
    kind: CircuitKind
    rooms: tuple[str, ...] = ()
    manifold: str | None = None
    """Manifold key (scope ``manifold``) for ``MIXING_MANIFOLD`` circuits."""

    def __post_init__(self) -> None:
        if (self.kind is CircuitKind.MIXING_MANIFOLD) != (self.manifold is not None):
            raise ValueError("CircuitFacts: manifold is required for (only) mixing circuits")


@dataclass(frozen=True, slots=True)
class BoilerFacts:
    """Known boiler specifications; ``None`` means explicitly unknown (FR-03)."""

    model: str | None = None
    max_flow_c: float | None = None
    max_ch_power_kw: float | None = None
    min_power_kw: float | None = None
    pump_setting: str | None = None


@dataclass(frozen=True, slots=True)
class InstallationFacts:
    """Read-only view of the installation profile (FR-02/03) for rule predicates."""

    boiler: BoilerFacts = field(default_factory=BoilerFacts)
    circuits: tuple[CircuitFacts, ...] = ()
    rooms: tuple[str, ...] = ()
    zones: tuple[str, ...] = ()
    loops: tuple[str, ...] = ()
    version: str = ""
    """Profile version, part of the advice snapshot (FR-41)."""
    known_specs: frozenset[str] = frozenset()
    """Keys of boiler-level specifications with an explicitly known value (FR-03)."""
    modulation_kw_per_pct: float | None = None
    """kW per modulation percent; set only from a validated conversion, else ``None``."""

    @property
    def has_mixing_manifold(self) -> bool:
        return any(c.kind is CircuitKind.MIXING_MANIFOLD for c in self.circuits)

    @property
    def has_direct_circuit(self) -> bool:
        return any(c.kind is CircuitKind.DIRECT for c in self.circuits)

    @property
    def manifolds(self) -> tuple[str, ...]:
        return tuple(sorted({c.manifold for c in self.circuits if c.manifold is not None}))

    def scope_keys(self, kind: ScopeKind) -> tuple[str, ...]:
        """Keys of the profile entities a scoped role is parametrised by."""
        if kind is ScopeKind.ROOM:
            return tuple(sorted(self.rooms))
        if kind is ScopeKind.ZONE:
            return tuple(sorted(self.zones))
        if kind is ScopeKind.MANIFOLD:
            return self.manifolds
        if kind is ScopeKind.CIRCUIT:
            return tuple(sorted(c.key for c in self.circuits))
        if kind is ScopeKind.LOOP:
            return tuple(sorted(self.loops))
        return ()


# --------------------------------------------------------------------------------------
# Special periods (FR-10, mapped from the store by #21)
# --------------------------------------------------------------------------------------


class SpecialPeriodKind(StrEnum):
    COMMISSIONING = "commissioning"
    """Opstookprotocol."""
    MAINTENANCE = "maintenance"
    VENTING = "venting"
    """Ontluchten."""
    TEST = "test"
    VACATION = "vacation"
    SPECIAL_USE = "special_use"


@dataclass(frozen=True, slots=True)
class SpecialPeriod:
    """A marked period. ``excluded`` periods stay visible but are left out of normal
    behaviour and before/after comparisons by default (FR-10)."""

    range: TimeRange
    kind: SpecialPeriodKind
    excluded: bool = True


# --------------------------------------------------------------------------------------
# Signal status and availability (computed in cvidee.rules.availability)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignalStatus:
    """State of one *mapped* signal over the assessment window. Unmapped signals are
    simply absent from the status collection."""

    signal: SignalRef
    coverage: float
    """Fraction of the assessment window with a known value, ``[0, 1]``."""
    stale: bool = False
    """Currently older than its max age (only meaningful with ``heartbeat_expected``)."""
    resolution_ms: DurationMs | None = None
    """Actual update resolution (e.g. median report interval); ``None`` = not determined."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("SignalStatus: coverage must be within [0, 1]")
        if self.resolution_ms is not None and self.resolution_ms <= 0:
            raise ValueError("SignalStatus: resolution must be positive")


class AvailabilityStatus(StrEnum):
    """Beschikbaar / beperkt / niet beschikbaar (FR-04). Ordered by strength."""

    AVAILABLE = "available"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"

    @property
    def rank(self) -> int:
        """0 = available, 2 = unavailable."""
        return _AVAILABILITY_ORDER.index(self)

    def worst(self, other: AvailabilityStatus) -> AvailabilityStatus:
        return self if self.rank >= other.rank else other


_AVAILABILITY_ORDER: tuple[AvailabilityStatus, ...] = (
    AvailabilityStatus.AVAILABLE,
    AvailabilityStatus.LIMITED,
    AvailabilityStatus.UNAVAILABLE,
)


class AnalysisId(StrEnum):
    """Analyses with an availability status (design v3 ``ANALYSES``)."""

    CYCLES = "cycles"
    """Cycli."""
    TEMPERATURE = "temperature"
    """Temperatuur."""
    OPERATING_MODE = "operating_mode"
    """Bedrijfsmodus."""
    COMFORT = "comfort"
    """Comfort."""
    ZONES = "zones"
    """Zones."""
    HYDRAULIC = "hydraulic"
    """Hydraulisch."""
    CONSUMPTION = "consumption"
    """Verbruik."""
    EFFICIENCY = "efficiency"
    """Rendement."""
    BEFORE_AFTER = "before_after"
    """Voor/na-evaluatie van vastgelegde wijzigingen."""


class IssueKind(StrEnum):
    """Why an analysis or rule is limited or unavailable."""

    NOT_MAPPED = "not_mapped"
    NO_DATA = "no_data"
    """Mapped, but no known value at all in the assessment window."""
    LOW_COVERAGE = "low_coverage"
    STALE = "stale"
    RESOLUTION = "resolution"
    """Actual resolution coarser than required."""
    RESOLUTION_UNKNOWN = "resolution_unknown"
    NO_SCOPE_IN_PROFILE = "no_scope_in_profile"
    """A per-room/zone/manifold role, but the profile has no such entity."""
    NO_CHANGE_DATA = "no_change_data"
    INSUFFICIENT_COMPARISON_EVIDENCE = "insufficient_comparison_evidence"
    OVERLAPPING_CHANGES = "overlapping_changes"
    WEATHER_NOT_COMPARABLE = "weather_not_comparable"
    SETPOINTS_NOT_COMPARABLE = "setpoints_not_comparable"


@dataclass(frozen=True, slots=True, order=True)
class AvailabilityIssue:
    """One structured reason (no UI text: the API/UI renders it in Dutch)."""

    kind: IssueKind
    role: Role | None = None
    scope_key: str | None = None
    required: bool = True
    """``False`` for optional signals (they can only make an analysis limited)."""


@dataclass(frozen=True, slots=True)
class Availability:
    """Availability of an analysis or rule (FR-04)."""

    status: AvailabilityStatus
    issues: tuple[AvailabilityIssue, ...] = ()

    @property
    def missing_signals(self) -> tuple[SignalRef, ...]:
        """Required and optional signals that are not mapped or have no data."""
        return self._missing(required_only=False)

    @property
    def missing_required(self) -> tuple[SignalRef, ...]:
        """Required signals that are missing (for "Ontbreekt: …" when unavailable)."""
        return self._missing(required_only=True)

    def _missing(self, *, required_only: bool) -> tuple[SignalRef, ...]:
        refs: set[SignalRef] = set()
        for issue in self.issues:
            if (
                issue.role is not None
                and issue.kind in (IssueKind.NOT_MAPPED, IssueKind.NO_DATA)
                and (issue.required or not required_only)
            ):
                refs.add(signal_ref(issue.role, issue.scope_key))
        return tuple(sorted(refs))


def signal_ref(role: Role, scope_key: str | None = None) -> SignalRef:
    """The concrete signal for ``role`` (singleton scopes ignore ``scope_key``)."""
    kind = role.scope_kind
    if kind is ScopeKind.BOILER:
        return SignalRef(role, BOILER)
    if kind is ScopeKind.OUTDOOR:
        return SignalRef(role, OUTDOOR)
    if scope_key is None:
        raise ValueError(f"role {role} needs a scope key")
    return SignalRef(role, Scope(kind, scope_key))


@dataclass(frozen=True, slots=True)
class AnalysisAvailability:
    analysis: AnalysisId
    availability: Availability


# --------------------------------------------------------------------------------------
# Rule context
# --------------------------------------------------------------------------------------


class TimelineSource(Protocol):
    """Lazy access to signal timelines (the runner backs this with the store; tests use
    :class:`StaticTimelines`). Must be deterministic for a given run."""

    def timeline(self, signal: SignalRef, rng: TimeRange) -> SignalTimeline | None:
        """Timeline of ``signal`` covering ``rng``; ``None`` if the signal is not mapped."""
        ...


@dataclass(frozen=True, slots=True)
class StaticTimelines:
    """In-memory :class:`TimelineSource` (tests, small evaluations)."""

    timelines: tuple[SignalTimeline, ...] = ()

    def timeline(self, signal: SignalRef, rng: TimeRange) -> SignalTimeline | None:
        for tl in self.timelines:
            if tl.signal == signal:
                return tl
        return None


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a rule may read for one evaluation (ADR-004 §3).

    The runner builds one context per evaluation from stored derived data; it is
    immutable and independent of persistence. Collections are sorted by start.
    """

    now: TimestampMs
    period: TimeRange
    """Evaluation period ``[now - history, horizon)``; rules take sub-windows of it."""
    profile: InstallationFacts
    signals: tuple[SignalStatus, ...] = ()
    gateway_signals: tuple[SignalRef, ...] = ()
    """Mapped signals explicitly configured as arriving through the CAN gateway."""
    """Status of every mapped signal over the evaluation period."""
    availability: tuple[AnalysisAvailability, ...] = ()
    cycles: tuple[BurnerCycle, ...] = ()
    mode_segments: tuple[ModeSegment, ...] = ()
    metrics: tuple[MetricValue, ...] = ()
    quality_events: tuple[QualityEvent, ...] = ()
    special_periods: tuple[SpecialPeriod, ...] = ()
    timelines: TimelineSource = field(default_factory=StaticTimelines)
    config_hash: str = ""
    change_evaluations: tuple[EvaluationFact, ...] = ()
    room_comfort: tuple[tuple[str, RoomComfortMetrics], ...] = ()
    allowed_room_comfort_loss_h_week: float = 4.0
    minimum_room_comfort_coverage: float = 0.8
    minimum_room_comfort_observed_hours: float = 6.0
    tz: str = LOCAL_TZ

    # -- signals -------------------------------------------------------------------------

    def signal_status(self, signal: SignalRef) -> SignalStatus | None:
        for status in self.signals:
            if status.signal == signal:
                return status
        return None

    def is_mapped(self, signal: SignalRef) -> bool:
        return self.signal_status(signal) is not None

    def unmapped(self, signals: Sequence[SignalRef]) -> tuple[SignalRef, ...]:
        """The given signals that are not mapped, sorted (for ``missing_signals``)."""
        return tuple(sorted(s for s in signals if not self.is_mapped(s)))

    def availability_of(self, analysis: AnalysisId) -> Availability | None:
        for item in self.availability:
            if item.analysis is analysis:
                return item.availability
        return None

    def timeline(self, signal: SignalRef, rng: TimeRange | None = None) -> SignalTimeline | None:
        return self.timelines.timeline(signal, rng or self.period)

    # -- exclusions ----------------------------------------------------------------------

    def excluded_ranges(self, rng: TimeRange | None = None) -> tuple[TimeRange, ...]:
        """Excluded special periods clipped to ``rng`` (default: the evaluation period)."""
        window = rng or self.period
        out: list[TimeRange] = []
        for sp in self.special_periods:
            if sp.excluded:
                clipped = sp.range.intersect(window)
                if clipped is not None:
                    out.append(clipped)
        return tuple(sorted(out, key=lambda r: (r.start, r.end)))

    def is_excluded(self, rng: TimeRange) -> bool:
        """Whether ``rng`` overlaps an excluded special period."""
        return any(sp.excluded and sp.range.overlaps(rng) for sp in self.special_periods)

    # -- cycles --------------------------------------------------------------------------

    def cycles_in(self, rng: TimeRange | None = None) -> Iterator[BurnerCycle]:
        """Cycles whose start lies in ``rng`` (default: the evaluation period)."""
        window = rng or self.period
        for cycle in self.cycles:
            if window.contains(cycle.start):
                yield cycle

    def relevant_cycles(
        self, modes: frozenset[Mode] = frozenset({Mode.CH}), rng: TimeRange | None = None
    ) -> tuple[BurnerCycle, ...]:
        """Cycles in ``modes`` that do not overlap an excluded special period (ADR-004 §3.3).

        DHW cycles are excluded by default because ``modes`` defaults to ``{CH}``.
        """
        return tuple(
            c
            for c in self.cycles_in(rng)
            if c.mode in modes and not self.is_excluded(_cycle_range(c, self.period.end))
        )

    def excluded_cycles(
        self, modes: frozenset[Mode] = frozenset({Mode.CH}), rng: TimeRange | None = None
    ) -> tuple[BurnerCycle, ...]:
        """Cycles left out by :meth:`relevant_cycles` (shown as "… uitgesloten")."""
        relevant = set(self.relevant_cycles(modes, rng))
        return tuple(c for c in self.cycles_in(rng) if c not in relevant)

    # -- metrics and quality ---------------------------------------------------------------

    def metrics_named(self, name: MetricName, mode: Mode | None = None) -> tuple[MetricValue, ...]:
        return tuple(m for m in self.metrics if m.name is name and m.mode is mode)

    def quality_events_of(self, *kinds: QualityEventKind) -> tuple[QualityEvent, ...]:
        return tuple(e for e in self.quality_events if not kinds or e.kind in kinds)

    # -- local days (repetition over days) -------------------------------------------------

    def local_days(self, rng: TimeRange | None = None) -> tuple[TimeRange, ...]:
        """``Europe/Amsterdam`` calendar days intersecting ``rng``, clipped to it (23/25 h
        on DST days)."""
        return local_days(rng or self.period, self.tz)


def _cycle_range(cycle: BurnerCycle, horizon: TimestampMs) -> TimeRange:
    end = cycle.end if cycle.end is not None else max(horizon, cycle.start + 1)
    return TimeRange(cycle.start, max(end, cycle.start + 1))


def local_days(rng: TimeRange, tz: str = LOCAL_TZ) -> tuple[TimeRange, ...]:
    """Local calendar days intersecting ``rng``, as UTC ms ranges clipped to ``rng``."""
    zone = ZoneInfo(tz)
    start_local = datetime.fromtimestamp(rng.start / 1000, UTC).astimezone(zone)
    day = start_local.date()
    out: list[TimeRange] = []
    while True:
        day_start = datetime(day.year, day.month, day.day, tzinfo=zone)
        nxt = day + timedelta(days=1)
        day_end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=zone)
        start_ms = int(day_start.timestamp() * 1000)
        end_ms = int(day_end.timestamp() * 1000)
        if start_ms >= rng.end:
            break
        clipped = TimeRange(start_ms, end_ms).intersect(rng)
        if clipped is not None:
            out.append(clipped)
        day = nxt
    return tuple(out)


# --------------------------------------------------------------------------------------
# Finding candidates
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """A possible explanation (FR-23). Texts are Dutch UI text."""

    name: str
    """E.g. "Te weinig open afgifte"."""
    evidence_for: str
    """Aanwijzing: what in the data points to this explanation."""
    missing: str
    """Ontbreekt: what is unknown or argues against it."""
    distinguishing_measurement: str
    """Onderscheidende meting: what would confirm or rule it out."""
    signals_needed: tuple[Role, ...] = ()
    """Roles that would provide the distinguishing measurement (link to "koppelen")."""


@dataclass(frozen=True, slots=True)
class CycleRef:
    """Evidence: one burner cycle (by its key, ``start``)."""

    cycle_start: TimestampMs


@dataclass(frozen=True, slots=True)
class PeriodRef:
    """Evidence: a time range, e.g. the pattern window or a data gap."""

    range: TimeRange
    label: str = ""


@dataclass(frozen=True, slots=True)
class SignalEvidence:
    """Evidence: a signal used for the conclusion, optionally limited to a range."""

    signal: SignalRef
    range: TimeRange | None = None
    assumed_unchanged: bool = False
    """The signal was combined via ``Alignment.ASSUMED_UNCHANGED`` (ADR-002 §7)."""


@dataclass(frozen=True, slots=True)
class MetricRef:
    """Evidence: a stored metric value (by its key)."""

    name: MetricName
    window_start: TimestampMs
    mode: Mode | None = None


@dataclass(frozen=True, slots=True)
class QualityEventRef:
    """Evidence: a quality event (by its key)."""

    kind: QualityEventKind
    start: TimestampMs
    signal: SignalRef | None = None


type EvidenceRef = CycleRef | PeriodRef | SignalEvidence | MetricRef | QualityEventRef
"""Link from a conclusion to the data it is based on (FR-37)."""


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    """Onderbouwing (FR-22): the facts the certainty is derived from, shown in the UI as
    dekking / relevante cycli / herhaling / ontbrekende signalen."""

    coverage: float
    """Known fraction of the relevant time for the core signals, ``[0, 1]``."""
    unknown_ms: DurationMs = 0
    """Unknown time within the period (shown as "· 30 min onbekend")."""
    excluded_ms: DurationMs = 0
    """Time excluded because of special periods."""
    excluded_cycles: int = 0
    """Cycles left out (DHW, special periods): "1 tapwatercyclus uitgesloten"."""
    relevant_cycles: int | None = None
    """Denominator: cycles the pattern is judged on ("van 24 cv-cycli"); ``None`` if not
    cycle-based."""
    pattern_cycles: int | None = None
    """Numerator: cycles showing the pattern ("18 van …")."""
    observed_hours: float | None = None
    repetition_days: int | None = None
    """Days on which the pattern occurred ("3 van laatste 7 dagen")."""
    repetition_window_days: int | None = None
    missing_signals: tuple[SignalRef, ...] = ()
    """Optional signals that would strengthen or discriminate the conclusion."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("EvidenceSummary: coverage must be within [0, 1]")
        if min(self.unknown_ms, self.excluded_ms, self.excluded_cycles) < 0:
            raise ValueError("EvidenceSummary: negative amounts")
        if (
            self.pattern_cycles is not None
            and self.relevant_cycles is not None
            and self.pattern_cycles > self.relevant_cycles
        ):
            raise ValueError("EvidenceSummary: pattern_cycles exceeds relevant_cycles")
        if (
            self.repetition_days is not None
            and self.repetition_window_days is not None
            and self.repetition_days > self.repetition_window_days
        ):
            raise ValueError("EvidenceSummary: repetition_days exceeds the window")
        if tuple(sorted(set(self.missing_signals))) != self.missing_signals:
            raise ValueError("EvidenceSummary: missing_signals must be sorted and unique")


class RecommendationKind(StrEnum):
    SETTING_CHANGE = "setting_change"
    """Instellingswijziging: needs a rollback criterion and at least moderate certainty."""
    CHECK = "check"
    """Controle zonder instellingswijziging."""
    MEASUREMENT = "measurement"
    """Aanvullende meting (FR-28)."""
    REVERT = "revert"
    """Terugdraaien of eerdere wijziging."""


@dataclass(frozen=True, slots=True)
class RecommendationDraft:
    """Advice in the required format of requirements §5 / FR-25 (Dutch UI texts).

    Title, relevance, observed pattern, period, signals, explanations and certainty come
    from the enclosing :class:`FindingCandidate`; the follow-up status is owned by the
    findings engine (#36) and starts as ``open``.
    """

    kind: RecommendationKind
    action: str
    """Concrete first action or additional measurement."""
    reason: str
    expected_effect: str
    comfort_impact: str
    conditions: str
    """Comparability conditions for the evaluation."""
    evaluation: str
    """Evaluation method and period."""
    success_criterion: str
    magnitude: str | None = None
    """Change size if it can be substantiated; ``None`` renders "Niet te onderbouwen met
    huidige gegevens — geen getal genoemd." (never an invented number)."""
    rollback_criterion: str | None = None
    """``None`` renders "N.v.t." and is only allowed for non-setting advice."""
    evaluation_days: int | None = None
    parameter: str | None = None
    """Setting the advice is about (links to the change log, FR-29)."""
    follow_up: str | None = None
    """Next step after the evaluation ("Daarna", design v3 B-011)."""

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("RecommendationDraft: action is required")
        if self.kind is RecommendationKind.SETTING_CHANGE and not self.rollback_criterion:
            raise ValueError("RecommendationDraft: a setting change needs a rollback criterion")
        if self.evaluation_days is not None and self.evaluation_days <= 0:
            raise ValueError("RecommendationDraft: evaluation_days must be positive")


@dataclass(frozen=True, slots=True)
class FindingCandidate:
    """What a rule emits; the findings engine (#34) turns candidates into findings.

    Dedupe key: ``(rule_id, scope_key)`` — the rule id is added by the registry. A new
    candidate with the same key updates the existing finding (FR-39).
    """

    scope_key: str
    """Stable within a rule, e.g. ``"boiler:ch"`` or ``"room:slaapkamer"``; never contains
    a timestamp (one finding per problem, not per cycle)."""
    category: Category
    title: str
    severity: Severity
    certainty: Certainty
    relevance: tuple[Relevance, ...]
    observation: str
    """Waarneming: measurements and period only, no explanation (FR-21)."""
    period: TimeRange
    signals: tuple[SignalRef, ...]
    evidence: EvidenceSummary
    interpretation: str = ""
    """Interpretatie: what the observation may mean; never states a cause as proven."""
    hypotheses: tuple[Hypothesis, ...] = ()
    recommendation: RecommendationDraft | None = None
    no_advice_reason: str = ""
    """Shown when there is no advice ("Geen optimalisatieadvies. …")."""
    refs: tuple[EvidenceRef, ...] = ()
    supports: tuple[str, ...] = ()
    """Rule ids this candidate can be bundled under as supporting evidence when scope and
    period overlap (FR-26), e.g. ``stop-tijdens-vraag`` supports ``kort-branden``."""

    def __post_init__(self) -> None:
        if not self.scope_key or any(c.isspace() for c in self.scope_key):
            raise ValueError("FindingCandidate: scope_key must be non-empty without spaces")
        if not self.title.strip() or not self.observation.strip():
            raise ValueError("FindingCandidate: title and observation are required")
        if not self.relevance and self.severity is not Severity.INFO:
            raise ValueError("FindingCandidate: relevance is required unless severity is info")
        if self.recommendation is None and not self.no_advice_reason.strip():
            raise ValueError("FindingCandidate: give a recommendation or a no-advice reason")
        weak = self.certainty in (Certainty.INSUFFICIENT_EVIDENCE, Certainty.PRELIMINARY)
        if (
            weak
            and self.recommendation is not None
            and self.recommendation.kind is RecommendationKind.SETTING_CHANGE
        ):
            raise ValueError(
                "FindingCandidate: no setting change on insufficient or preliminary evidence "
                "(FR-28: propose a check or measurement instead)"
            )
        if self.certainty is Certainty.INSUFFICIENT_EVIDENCE and (
            self.recommendation is None
            or self.recommendation.kind is not RecommendationKind.MEASUREMENT
        ):
            raise ValueError(
                "FindingCandidate: insufficient evidence requires an additional-measurement "
                "recommendation (FR-28, scenario 10)"
            )
        if tuple(sorted(set(self.supports))) != self.supports:
            raise ValueError("FindingCandidate: supports must be sorted and unique")


# --------------------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------------------


class ParamGroup(StrEnum):
    """``x-group``: section of the analysis settings screen (design additions §1.5)."""

    SHORT_CYCLES = "short_cycles"
    """Korte cycli."""
    COMFORT = "comfort"
    EFFECT_MEASUREMENT = "effect_measurement"
    """Effectmeting."""
    DATA = "data"
    """Gegevens."""
    RECOVERY = "recovery"
    """Herstel."""
    COSTS = "costs"
    """Kosten."""
    DISPLAY = "display"
    """Weergave."""


def param(
    default: Any,
    *,
    title: str,
    description: str,
    unit: str,
    group: ParamGroup,
    step: float | None = None,
    ge: float | None = None,
    le: float | None = None,
) -> Any:
    """A rule parameter field with the ``x-*`` extensions the settings UI renders.

    ``title`` and ``description`` are Dutch UI text. Values are stored in the unit shown
    (``unit``); rules convert to milliseconds themselves. The field name carries the unit
    as suffix (``short_cycle_min``) so conversions are explicit.
    """
    extra: dict[str, Any] = {"x-unit": unit, "x-group": str(group)}
    if step is not None:
        extra["x-step"] = step
    return Field(
        default=default,
        title=title,
        description=description,
        ge=ge,
        le=le,
        json_schema_extra=extra,
    )


class RuleParams(BaseModel):
    """Base class of every rule's ``params_schema``: immutable, no unknown keys."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class NoParams(RuleParams):
    """For rules without configurable parameters."""


# --------------------------------------------------------------------------------------
# Certainty criteria template (filled per rule, documented in docs/regels/<id>.md)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Thresholds:
    """A row of the criteria template; ``None`` = not applicable for this rule."""

    coverage: float | None = None
    relevant_cycles: int | None = None
    observed_hours: float | None = None
    repetition_days: int | None = None

    def __post_init__(self) -> None:
        if self.coverage is not None and not 0.0 <= self.coverage <= 1.0:
            raise ValueError("Thresholds: coverage must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class CertaintyCriteria:
    """Criteria template each rule fills (ADR-004 §5). No percentages are reported; the
    thresholds only decide the category."""

    minimum: Thresholds
    """Below any of these → ``INSUFFICIENT_EVIDENCE``."""
    structural_repetition_days: int | None = None
    """Pattern on fewer days → ``PRELIMINARY`` ("voorlopig"); ``None`` = not day-based."""
    repetition_window_days: int | None = None
    reasonable: Thresholds | None = None
    """All met → at least ``REASONABLE``, else ``MODERATE``. ``None`` = not reachable;
    ``Thresholds()`` (all ``None``) = reached as soon as the pattern is structural."""
    high: Thresholds | None = None
    """All met (on top of ``reasonable``) → ``HIGH``. ``None`` = not reachable."""
    allow_measured: bool = False
    """Direct measurements of this rule may reach ``HIGH_MEASURED``."""
    lower_for_missing_signals: bool = True
    """Whether unmeasured optional signals weaken certainty for this rule's observation."""
    max_certainty: Certainty = Certainty.HIGH_MEASURED
    """Cap, e.g. rules that only correlate stay at most ``REASONABLE``."""

    def __post_init__(self) -> None:
        if (self.structural_repetition_days is None) != (self.repetition_window_days is None):
            raise ValueError("CertaintyCriteria: repetition days and window go together")
        if (
            self.structural_repetition_days is not None
            and self.repetition_window_days is not None
            and self.structural_repetition_days > self.repetition_window_days
        ):
            raise ValueError("CertaintyCriteria: repetition days exceed the window")
        if self.high is not None and self.reasonable is None:
            raise ValueError("CertaintyCriteria: 'high' requires 'reasonable'")


# --------------------------------------------------------------------------------------
# Rule protocol
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolutionLimit:
    """A signal must update at least every ``max_interval_ms``; otherwise the analysis or
    rule becomes ``on_exceed`` (FR-11 §3: resolution must distinguish cycle limits)."""

    role: Role
    max_interval_ms: DurationMs
    on_exceed: AvailabilityStatus = AvailabilityStatus.LIMITED

    def __post_init__(self) -> None:
        if self.max_interval_ms <= 0:
            raise ValueError("ResolutionLimit: max_interval_ms must be positive")
        if self.on_exceed is AvailabilityStatus.AVAILABLE:
            raise ValueError("ResolutionLimit: on_exceed must be limited or unavailable")


class Rule(Protocol):
    """A versioned detection rule (technical plan §3.4, ADR-004 §2)."""

    @property
    def id(self) -> str:
        """Kebab-case id from design v3, e.g. ``kort-branden``. Never changes."""
        ...

    @property
    def version(self) -> str:
        """Semantic version ``MAJOR.MINOR.PATCH`` (ADR-004 §7)."""
        ...

    @property
    def category(self) -> Category: ...

    @property
    def required_signals(self) -> frozenset[Role]:
        """Missing → rule not evaluated (unavailable, FR-04)."""
        ...

    @property
    def optional_signals(self) -> frozenset[Role]:
        """Missing → rule limited; listed in ``missing_signals``, lowers certainty."""
        ...

    @property
    def applies_in_modes(self) -> frozenset[Mode]:
        """Operating modes whose data the rule judges (FR-09, §4 requirements)."""
        ...

    @property
    def params_schema(self) -> type[RuleParams]: ...

    def applies_to(self, profile: InstallationFacts) -> bool:
        """Installation predicate, e.g. "not for a mixing-manifold circuit" (FR-02)."""
        ...

    def resolution_limits(self, params: RuleParams) -> tuple[ResolutionLimit, ...]: ...

    def history_ms(self, params: RuleParams) -> DurationMs:
        """Length of the evaluation period the rule needs before ``now``."""
        ...

    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria: ...

    def evaluate(self, ctx: RuleContext, params: RuleParams) -> Sequence[FindingCandidate]:
        """Pure evaluation. Must be deterministic and independent of input order."""
        ...

    def unavailable_evidence(
        self, ctx: RuleContext, params: RuleParams
    ) -> Sequence[FindingCandidate]:
        """Optional measurement-only findings when required signals are unavailable."""
        ...


class BaseRule[P: RuleParams](ABC):
    """Convenience base implementing :class:`Rule` with typed parameters.

    Subclasses set the class attributes and implement :meth:`_evaluate` (and optionally
    the other hooks) against their own parameter type ``P``.
    """

    id: ClassVar[str]
    version: ClassVar[str]
    category: ClassVar[Category]
    required_signals: ClassVar[frozenset[Role]]
    optional_signals: ClassVar[frozenset[Role]] = frozenset()
    applies_in_modes: ClassVar[frozenset[Mode]] = frozenset({Mode.CH})
    params_schema: ClassVar[type[RuleParams]]

    def applies_to(self, profile: InstallationFacts) -> bool:
        del profile
        return True

    def resolution_limits(self, params: RuleParams) -> tuple[ResolutionLimit, ...]:
        del params
        return ()

    @abstractmethod
    def history_ms(self, params: RuleParams) -> DurationMs: ...

    @abstractmethod
    def certainty_criteria(self, params: RuleParams) -> CertaintyCriteria: ...

    def evaluate(self, ctx: RuleContext, params: RuleParams) -> Sequence[FindingCandidate]:
        return self._evaluate(ctx, self.typed(params))

    def unavailable_evidence(
        self, ctx: RuleContext, params: RuleParams
    ) -> Sequence[FindingCandidate]:
        """Optional measurement-only outcomes when required signals are unavailable.

        These candidates are persisted without treating the rule as evaluated, so they
        cannot resolve a prior diagnostic finding.
        """
        del ctx, params
        return ()

    def typed(self, params: RuleParams) -> P:
        """``params`` as this rule's parameter type (validated if another type is given)."""
        if not isinstance(params, self.params_schema):
            params = self.params_schema.model_validate(params.model_dump())
        return cast("P", params)

    @abstractmethod
    def _evaluate(self, ctx: RuleContext, params: P) -> Sequence[FindingCandidate]: ...


def validate_rule_identity(rule: Rule) -> None:
    """Check id and version format (registry invariant)."""
    if not RULE_ID_PATTERN.match(rule.id):
        raise ValueError(f"rule id {rule.id!r} must be kebab-case (e.g. 'kort-branden')")
    if not SEMVER_PATTERN.match(rule.version):
        raise ValueError(f"rule {rule.id}: version {rule.version!r} is not MAJOR.MINOR.PATCH")
    overlap = rule.required_signals & rule.optional_signals
    if overlap:
        raise ValueError(f"rule {rule.id}: roles both required and optional: {sorted(overlap)}")


def display_version(version: str) -> str:
    """UI form "v1.3" (major.minor; patch releases never change output)."""
    major, minor, _ = version.split(".")
    return f"v{major}.{minor}"


def scope_key_for(signal_scope: ScopeKind, key: str | None = None, *parts: str) -> str:
    """Build a stable ``scope_key`` like ``boiler:ch`` or ``room:slaapkamer``."""
    head = str(signal_scope) if key is None else f"{signal_scope}:{key}"
    return ":".join((head, *parts))
