"""``GET /api/status`` and ``GET /api/overview`` (FR-04, FR-36, design additions §2, §5c)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from cvidee.api.schemas.common import Action, ApiModel, TimeRange, UtcDateTime
from cvidee.api.schemas.findings import FindingSummary
from cvidee.api.schemas.signals import AnalysisOut
from cvidee.store.enums import Mode, RunStatus


class LiveState(StrEnum):
    """Header status pill (design additions §0.3); 'app unreachable' is client-side."""

    LIVE = "live"
    DELAYED = "delayed"
    HA_OFFLINE = "ha_offline"
    IMPORTING = "importing"
    RECOMPUTING = "recomputing"


class LiveStatus(ApiModel):
    state: LiveState
    last_data_at: UtcDateTime | None = Field(description="Newest observation received.")
    since: UtcDateTime | None = Field(
        default=None, description="Start of the current non-live state (e.g. HA offline)."
    )
    progress_pct: float | None = Field(
        default=None, ge=0, le=100, description="Progress while importing or recomputing."
    )


class SetupState(ApiModel):
    """First-run setup progress (design additions §2)."""

    onboarding_done: bool
    onboarding_completed_at: UtcDateTime | None = None
    flame_mapped: bool
    history_imported: bool
    steps_done: int = Field(ge=0, le=3)
    steps_total: Literal[3] = 3


class HaConnectionState(StrEnum):
    CONNECTED = "connected"
    CONNECTING = "connecting"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"


class HaStatus(ApiModel):
    state: HaConnectionState
    deployment: Literal["addon", "standalone"]
    version: str | None = Field(description="Home Assistant version when connected.")
    url: str | None = Field(default=None, description="HA_URL in standalone mode.")
    entity_count: int | None = Field(default=None, ge=0)
    since: UtcDateTime | None = Field(default=None, description="Time of the last state change.")


class MqttStatus(ApiModel):
    broker_found: bool
    connected: bool
    export_mode: Literal["mqtt", "fallback", "none"] = Field(
        description="How summaries reach Home Assistant (FR-38)."
    )


class RecomputeStatus(ApiModel):
    status: RunStatus
    progress_pct: float | None = Field(default=None, ge=0, le=100)
    started_at: UtcDateTime | None = None
    reason_text: str | None = None


class ShellCounts(ApiModel):
    """Counters in the navigation (open findings, linked signals)."""

    open_findings: int = Field(ge=0)
    signals_linked: int = Field(ge=0)
    signals_total: int = Field(ge=0)


class StatusResponse(ApiModel):
    now: UtcDateTime
    stub_data: bool = Field(description="True when serving example data (header pill).")
    live: LiveStatus
    source_text: str = Field(description="Data source in the header, e.g. 'CAN-bus via HA'.")
    operating_mode: Mode
    operating_mode_since: UtcDateTime | None = None
    coverage_today_pct: float | None = Field(ge=0, le=100)
    counts: ShellCounts
    setup: SetupState
    ha: HaStatus
    mqtt: MqttStatus
    recompute: RecomputeStatus | None = None
    active_import_id: str | None = None


class AssessmentLevel(StrEnum):
    """Overall judgement level (§5c); ``insufficient_data`` forbids any green verdict."""

    INSUFFICIENT_DATA = "insufficient_data"
    LIMITED = "limited"
    SUFFICIENT = "sufficient"


class AssessmentReasonCode(StrEnum):
    # Reasons for insufficient_data (§5c)
    FLAME_NOT_MAPPED = "flame_not_mapped"
    TOO_FEW_HOURS = "too_few_hours"
    LOW_COVERAGE = "low_coverage"
    NO_DATA_YET = "no_data_yet"
    # Reasons for limited
    HA_DISCONNECTED = "ha_disconnected"
    DATA_GAP = "data_gap"
    STALE_SIGNAL = "stale_signal"
    SIGNALS_NOT_MAPPED = "signals_not_mapped"


class AssessmentReason(ApiModel):
    code: AssessmentReasonCode
    text: str = Field(description="Dutch display text, e.g. 'Pas 2 van 6 uur met gegevens.'")
    action: Action | None = None


class Assessment(ApiModel):
    """``beoordeling`` of design additions §5c."""

    level: AssessmentLevel
    reasons: list[AssessmentReason]
    observed_hours: float = Field(ge=0)
    minimum_hours: float = Field(ge=0)
    coverage_pct: float | None = Field(ge=0, le=100)


class LiveValue(ApiModel):
    """KPI tile with a current measurement; ``value`` is ``null`` when unknown (§5a rule 5)."""

    key: str = Field(description="Stable key, e.g. 'flow_temperature' or 'room:slaapkamer'.")
    signal_id: str | None
    label: str
    value: float | None
    unit: str
    note_text: str = Field(description="Sub line, e.g. 'gemeten · 4 s' or 'niet gekoppeld'.")
    explanation: str = Field(description="KPI explanation (shown when 'uitleg tonen' is on).")
    stale: bool = False


class StatusCard(ApiModel):
    mode: Mode
    title: str
    text: str


class NextAction(ApiModel):
    """'Aanbevolen actie' (or 'Eerste stap' while setup is incomplete)."""

    kind: Literal["recommendation", "setup"]
    title: str
    text: str
    finding_id: str | None = None
    action: Action | None = None


class FindingsOverview(ApiModel):
    open_count: int = Field(ge=0)
    action_required_count: int = Field(ge=0, description="High-severity or rollback findings.")
    items: list[FindingSummary]


class DataQualityIssue(ApiModel):
    title: str = Field(description="E.g. 'CAN-uitval'.")
    value_text: str = Field(description="E.g. '10:10-10:40'.")
    severity: Literal["high", "medium", "info"]


class DataQualityOverview(ApiModel):
    coverage_pct: float | None = Field(ge=0, le=100, description="Core signals, today.")
    level: AssessmentLevel
    text: str
    issues: list[DataQualityIssue]


class TodaySummary(ApiModel):
    """Caption of the mini timeline ('Vandaag 06:00-12:00 · 24 cycli · 14 kort …')."""

    range: TimeRange
    ch_cycles: int = Field(ge=0)
    short_during_demand: int = Field(ge=0)


class OverviewResponse(ApiModel):
    window: TimeRange = Field(description="Analysed window (also the mini timeline range).")
    assessment: Assessment
    setup: SetupState
    status_card: StatusCard
    today: TodaySummary
    next_action: NextAction | None
    kpis: list[LiveValue]
    findings: FindingsOverview
    data_quality: DataQualityOverview
    analyses: list[AnalysisOut]
