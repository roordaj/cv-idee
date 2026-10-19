"""Example data from design v3 (FINDINGS, CHANGES, HISTORY, SIGNALS, ANALYSES, …).

Texts are copied verbatim from ``docs/design/CV-analyse-v3.dc.html``; numbers that v3
derives from ``buildSim()`` come from :mod:`cvidee.api.stubs.sim`. "Now" is Sunday
4 October 2026 12:00 Europe/Amsterdam.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from cvidee.analysis.types import Role, ScopeKind
from cvidee.api.schemas.changes import (
    Change,
    ChangeEvaluation,
    Comparability,
    ConditionRow,
    MetricAssessment,
    MetricComparison,
)
from cvidee.api.schemas.common import Action, TimeRange
from cvidee.api.schemas.data import (
    CoverageSegment,
    CoverageSegmentKind,
    Cycle,
    CycleClass,
    CycleSummary,
    DemandSegment,
    ImportJob,
    ImportSignalProgress,
    ModeSegment,
    ModeShare,
    PeriodExclusions,
    QualityEvent,
    SampledSeries,
    SignalCoverage,
    SpecialPeriod,
)
from cvidee.api.schemas.findings import (
    BundledEvidence,
    Evidence,
    EvidenceDisplay,
    FindingDetail,
    GlossaryTerm,
    HistoryEntry,
    HypothesisOut,
    RecommendationOut,
    RuleRef,
)
from cvidee.api.schemas.installation import (
    BoilerInfo,
    Circuit,
    InstallationProfile,
    Room,
    RoomComfort,
    RoomComfortWindow,
    Specification,
    Zone,
)
from cvidee.api.schemas.notifications import (
    HaExportEntity,
    Notification,
    NotificationPolicy,
    SeverityChannels,
)
from cvidee.api.schemas.signals import (
    AnalysisOut,
    Signal,
    SignalGroup,
    SignalState,
    ValueKindName,
)
from cvidee.api.schemas.system import (
    Assessment,
    AssessmentLevel,
    AssessmentReason,
    AssessmentReasonCode,
    DataQualityIssue,
    DataQualityOverview,
    LiveValue,
    NextAction,
    StatusCard,
)
from cvidee.api.stubs.sim import (
    END_MINUTE,
    GAP,
    SimCycle,
    at,
    build_sim,
    fmt_duration,
    js_round,
    nl,
)
from cvidee.rules.base import (
    AnalysisId,
    AvailabilityStatus,
    Category,
    RecommendationKind,
    Relevance,
)
from cvidee.store.enums import (
    Certainty,
    ChangeActor,
    CircuitKind,
    DeliveryStatus,
    EmitterType,
    EndReason,
    EvaluationVerdict,
    ImportStatus,
    Mode,
    NotificationChannel,
    NotificationKind,
    QualityEventKind,
    RecommendationOutcome,
    RecommendationStatus,
    Severity,
    SpecialPeriodKind,
    SpecStatus,
    TriState,
)

AMS = ZoneInfo("Europe/Amsterdam")
NOW = datetime(2026, 10, 4, 10, 0, tzinfo=UTC)
"""Sunday 4 October 2026 12:00 local."""
MONTHS = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def local(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """A Europe/Amsterdam wall-clock time as aware datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=AMS)


def day_month(value: datetime) -> str:
    """'11 okt' in local time."""
    loc = value.astimezone(AMS)
    return f"{loc.day} {MONTHS[loc.month - 1]}"


SOURCE_TEXT = "CAN-bus via Home Assistant"
WINDOW = TimeRange(start=at(0), end=at(END_MINUTE))
SHORT_CYCLE_THRESHOLD_S = 180.0

# --- signals (SIGNALS) -----------------------------------------------------------------

_KIND: dict[str, ValueKindName] = {"Gemeten": "measured", "Gerapporteerd": "reported"}


def _seconds(text: str) -> int | None:
    number, _, unit = text.partition(" ")
    if not number.isdigit():
        return None
    return int(number) * {"s": 1, "min": 60, "u": 3600}[unit]


_SIGNAL_ROWS: list[tuple[Role, str | None, SignalGroup, tuple[str, ...]]] = [
    # role, scope key, group, v3 row (naam, ent, loc, soort, age, st, nodig, unit, max, bet)
    (Role.FLAME, None, SignalGroup.REQUIRED, ("Brander/vlam actief", "binary_sensor.remeha_flame", "Ketel", "Gerapporteerd", "4 s", "ok", "Cycli-analyse", "—", "30 s", "Werkelijke vlam, niet het startcommando.")),
    (Role.OPERATING_MODE, None, SignalGroup.RECOMMENDED, ("CV-/tapwatermodus", "sensor.remeha_status", "Ketel", "Gerapporteerd", "4 s", "ok", "Verwarmingsanalyse", "—", "30 s", "Statuscode ketel; 1 = CV, 2 = tapwater.")),
    (Role.FLOW_SETPOINT, None, SignalGroup.RECOMMENDED, ("Gewenste ketelaanvoer", "sensor.remeha_flow_setpoint", "Ketel", "Gerapporteerd", "4 s", "ok", "Diagnose korte cycli", "°C", "30 s", "Door eTwist gevraagde aanvoertemperatuur.")),
    (Role.FLOW_TEMPERATURE, None, SignalGroup.RECOMMENDED, ("Ketelaanvoer", "sensor.remeha_flow_temp", "Ketel uitgang", "Gemeten", "4 s", "ok", "Temperatuuranalyse", "°C", "30 s", "Interne aanvoersensor van de ketel.")),
    (Role.RETURN_TEMPERATURE, None, SignalGroup.RECOMMENDED, ("Ketelretour", "sensor.remeha_return_temp", "Ketel ingang", "Gemeten", "4 s", "ok", "Temperatuuranalyse", "°C", "30 s", "Interne retoursensor van de ketel.")),
    (Role.MODULATION, None, SignalGroup.RECOMMENDED, ("Brander-modulatie", "sensor.remeha_modulation", "Ketel", "Gerapporteerd", "4 s", "ok", "Minimumlastgedrag", "%", "30 s", "Percentage van maximaal vermogen. Niet omgezet naar kW.")),
    (Role.ROOM_TEMPERATURE, "woonkamer", SignalGroup.RECOMMENDED, ("Kamertemp. woonkamer", "sensor.etwist_woonkamer", "Woonkamer", "Gemeten", "2 min", "ok", "Comfortanalyse", "°C", "10 min", "Sensor in eTwist-thermostaat.")),
    (Role.ROOM_TEMPERATURE, "slaapkamer", SignalGroup.OPTIONAL, ("Kamertemp. slaapkamer", "sensor.slaapkamer_temp", "Slaapkamer boven", "Gemeten", "14 min", "stale", "Comfortanalyse boven", "°C", "10 min", "Zigbee-sensor, ophanghoogte 1,5 m.")),
    (Role.OUTDOOR_TEMPERATURE, None, SignalGroup.RECOMMENDED, ("Buitentemperatuur", "sensor.buiten_temp", "Noordgevel", "Gemeten", "5 min", "ok", "Weerscorrectie", "°C", "15 min", "Buitenvoeler, niet in de zon.")),
    (Role.MANIFOLD_FLOW_TEMPERATURE, "boven", SignalGroup.OPTIONAL, ("Verdeleraanvoer boven", "", "—", "—", "Niet gekoppeld", "none", "Hydraulische analyse", "°C", "1 min", "")),
    (Role.MANIFOLD_RETURN_TEMPERATURE, "boven", SignalGroup.OPTIONAL, ("Verdelerretour boven", "", "—", "—", "Niet gekoppeld", "none", "Hydraulische analyse", "°C", "1 min", "")),
    (Role.ZONE_DEMAND, "boven", SignalGroup.OPTIONAL, ("Zonevraag / klepstatus", "", "—", "—", "Niet gekoppeld", "none", "Zoneanalyse, B-014", "—", "1 min", "")),
    (Role.PUMP_STATE, None, SignalGroup.OPTIONAL, ("Pompstatus / debiet", "", "—", "—", "Niet gekoppeld", "none", "Hydraulische analyse, B-014", "—", "1 min", "")),
    (Role.GAS_CUMULATIVE, None, SignalGroup.OPTIONAL, ("Cumulatief gasverbruik", "", "—", "—", "Niet gekoppeld", "none", "Verbruiksanalyse", "m³", "1 u", "")),
    (Role.HEAT_METER, None, SignalGroup.OPTIONAL, ("Warmtemeter", "", "—", "—", "Niet gekoppeld", "none", "Rendementsanalyse", "kWh", "1 u", "")),
]  # fmt: skip


def signal_id(role: Role, scope_key: str | None = None) -> str:
    """``SignalRef`` string form: ``<role>@<scope kind>[:<key>]``."""
    kind = role.scope_kind
    return f"{role}@{kind}" if scope_key is None else f"{role}@{kind}:{scope_key}"


FLAME = signal_id(Role.FLAME)
CAN_SIGNALS = [signal_id(role) for role, *_ in _SIGNAL_ROWS[:6]]


def signals() -> list[Signal]:
    result: list[Signal] = []
    for role, key, group, row in _SIGNAL_ROWS:
        name, ent, loc, kind, age, st, needed, unit, max_age, meaning = row
        boiler_can = role.scope_kind is ScopeKind.BOILER and bool(ent)
        result.append(
            Signal(
                id=signal_id(role, key),
                role=role,
                scope_kind=role.scope_kind,
                scope_key=key,
                name=name,
                group=group,
                entity_id=ent or None,
                unit=None if unit == "—" else unit,
                location=None if loc == "—" else loc,
                value_kind=_KIND.get(kind),
                meaning=meaning or None,
                needed_for_text=needed,
                max_age_s=_seconds(max_age),
                expects_regular_updates=role in (Role.ROOM_TEMPERATURE, Role.OUTDOOR_TEMPERATURE),
                state={"ok": SignalState.OK, "stale": SignalState.STALE}.get(
                    st, SignalState.MISSING
                ),
                age_s=_seconds(age),
                median_update_interval_s=4.0 if boiler_can else None,
            )
        )
    return result


# --- analyses (ANALYSES) ---------------------------------------------------------------

_MANIFOLD = [
    signal_id(Role.MANIFOLD_FLOW_TEMPERATURE, "boven"),
    signal_id(Role.MANIFOLD_RETURN_TEMPERATURE, "boven"),
]
_ZONE = signal_id(Role.ZONE_DEMAND, "boven")
_PUMP = signal_id(Role.PUMP_STATE)
_GAS = signal_id(Role.GAS_CUMULATIVE)
_HEAT = signal_id(Role.HEAT_METER)

_A, _L, _U = (
    AvailabilityStatus.AVAILABLE,
    AvailabilityStatus.LIMITED,
    AvailabilityStatus.UNAVAILABLE,
)


def analyses() -> list[AnalysisOut]:
    rows = [
        (AnalysisId.CYCLES, "Cycli", _A, "Vlamstatus 4 s resolutie. Zonder gasmeter blijft dit werken.", []),
        (AnalysisId.TEMPERATURE, "Temperatuur", _A, "Aanvoer, retour en gewenste aanvoer gekoppeld.", []),
        (AnalysisId.OPERATING_MODE, "Bedrijfsmodus", _A, "CV, tapwater, naloop en standby te scheiden.", []),
        (AnalysisId.COMFORT, "Comfort", _L, "Slaapkamersensor 14 min oud; kinderkamer en badkamer zonder sensor.", []),
        (AnalysisId.ZONES, "Zones", _U, "Ontbreekt: zonevraag of klepstatus.", [_ZONE]),
        (AnalysisId.HYDRAULIC, "Hydraulisch", _U, "Ontbreekt: verdeleraanvoer, -retour, debiet.", [*_MANIFOLD, _PUMP]),
        (AnalysisId.CONSUMPTION, "Verbruik", _U, "Ontbreekt: cumulatief gasverbruik.", [_GAS]),
        (AnalysisId.EFFICIENCY, "Rendement", _U, "Ontbreekt: gasverbruik én warmtemeter.", [_GAS, _HEAT]),
        (AnalysisId.BEFORE_AFTER, "Voor/na", _U, "Geen wijziging vastgelegd.", []),
    ]  # fmt: skip
    return [
        AnalysisOut(id=a, name=n, status=s, note=note, missing_signals=m)
        for a, n, s, note, m in rows
    ]


# --- findings (FINDINGS, STATUS, GLOSS, TERMS) -----------------------------------------

GLOSS = {
    "Pendelen": "De brander gaat herhaaldelijk kort aan en uit terwijl de thermostaat nog warmte vraagt. Meer starts betekent meestal meer slijtage en een lager rendement.",
    "Warmtevraag": "Het signaal van de thermostaat (eTwist) dat de ketel moet verwarmen.",
    "Gewenste aanvoer": "De aanvoertemperatuur die de thermostaat op dit moment aan de ketel vraagt.",
    "Modulatie": "Brandervermogen als % van het maximum. Onder het minimum kan de ketel niet verder terugregelen; dan schakelt hij aan en uit.",
    "Minimumvermogen": "Het laagste vermogen waarop de brander stabiel kan branden. Vraagt het huis minder, dan ontstaan korte cycli.",
    "ΔT": "Verschil tussen aanvoer- en retourtemperatuur: hoeveel het water onderweg is afgekoeld, dus hoeveel warmte is afgegeven.",
    "Max. aanvoer": "De hoogste temperatuur die de ketel voor verwarming mag leveren. Lager is vaak zuiniger, maar kan te weinig warmte geven.",
    "Setpoint": "De ingestelde doeltemperatuur van een ruimte.",
    "Terugdraaicriterium": "Een grens die je vooraf vastlegt. Wordt die overschreden, dan zet je de wijziging terug.",
    "Vloerverwarming": "Reageert traag en krijgt via de mengverdeler al een lagere temperatuur. Een lagere ketelaanvoer merk je daar vaak als eerste.",
    "CAN-bus": "De datalijn waarover de ketel zijn meetwaarden aan Home Assistant doorgeeft.",
    "Onbekende tijd": 'Tijd zonder gegevens. Telt niet als "brander uit", zodat statistieken niet vertekenen.',
    "Mengverdeler": "Mengt heet ketelwater met koeler retourwater tot een geschikte temperatuur voor de vloer. Dat circuit gedraagt zich daardoor anders dan de ketel.",
    "Tapwater": "Warm water voor kraan en douche. De ketel stookt dan heter; die cycli tellen niet mee in de cv-analyse.",
    "Naloop": "Na het branden draait de pomp nog even door om restwarmte uit de ketel af te voeren.",
}  # fmt: skip
TERMS = {
    "B-014": ["Pendelen", "Warmtevraag", "Gewenste aanvoer", "Modulatie", "Minimumvermogen", "ΔT"],
    "B-011": ["Max. aanvoer", "Setpoint", "Terugdraaicriterium", "Vloerverwarming"],
    "B-015": ["CAN-bus", "Onbekende tijd"],
    "B-012": ["Mengverdeler", "ΔT"],
    "B-016": ["Tapwater", "Naloop"],
}

INITIAL_STATUS = {
    "B-014": RecommendationStatus.OPEN,
    "B-011": RecommendationStatus.ROLLBACK_TRIGGERED,
    "B-015": RecommendationStatus.OPEN,
    "B-012": RecommendationStatus.OPEN,
    "B-016": RecommendationStatus.OPEN,
}


def status_text(status: RecommendationStatus, postponed_until: datetime | None) -> str:
    """STATUS labels of design v3."""
    if status is RecommendationStatus.POSTPONED:
        return f"Uitgesteld tot {day_month(postponed_until)}" if postponed_until else "Uitgesteld"
    return {
        RecommendationStatus.OPEN: "Open",
        RecommendationStatus.ACCEPTED: "Geaccepteerd",
        RecommendationStatus.DONE: "Uitgevoerd · evaluatie loopt",
        RecommendationStatus.REJECTED: "Afgewezen",
        RecommendationStatus.ROLLBACK_TRIGGERED: "Terugdraaicriterium geactiveerd",
    }[status]


def _glossary(finding_id: str) -> list[GlossaryTerm]:
    return [GlossaryTerm(term=t, definition=GLOSS[t]) for t in TERMS.get(finding_id, [])]


def findings() -> list[FindingDetail]:
    """The five v3 findings, in v3 order, with their initial status."""
    st = build_sim().stats
    short, ch_w = st.short_cycles, st.ch_cycles_before_gap
    med_pause = fmt_duration(st.median_pause_min)
    open_ = RecommendationStatus.OPEN

    b014 = FindingDetail(
        id="B-014", category=Category.CYCLES, when_text="vandaag 06:00–10:10",
        severity=Severity.HIGH, certainty=Certainty.MODERATE,
        relevance=[Relevance.OPERATIONAL_STABILITY, Relevance.ENERGY],
        rule=RuleRef(id="kort-branden", version="1.3"),
        title="Herhaald kort branden tijdens aanhoudende warmtevraag",
        period=TimeRange(start=at(0), end=at(GAP[0])),
        status=open_, status_text=status_text(open_, None),
        evidence=Evidence(
            coverage_pct=93, unknown_s=1800, excluded_cycles=1, relevant_cycles=ch_w,
            pattern_cycles=short, repetition_days=3, repetition_window_days=7,
            missing_signals=[_ZONE, *_MANIFOLD, _PUMP],
            display=EvidenceDisplay(
                coverage="93 % · 30 min onbekend", cycles=f"{short} van {ch_w} cv-cycli",
                repetition="3 van laatste 7 dagen", missing_signals="Zoneklep, verdeler, pomp",
            ),
        ),
        observation=f"In {short} van {ch_w} cv-cycli stopt de brander binnen 3 minuten terwijl de warmtevraag blijft bestaan. De werkelijke aanvoer overschrijdt de gewenste aanvoer (55 °C) vaak vlak vóór de stop; modulatie staat dan op het minimum (19 %).",
        period_text="Zo 4 okt 06:00–10:10 · 1 tapwatercyclus uitgesloten",
        signals_text="Vlamstatus, CV-modus, warmtevraag, gewenste en werkelijke aanvoer, modulatie",
        interpretation="Dit past bij onvoldoende warmteafgifte ten opzichte van het geleverde vermogen, maar bewijst de oorzaak niet. Drie verklaringen zijn mogelijk:",
        hypotheses=[
            HypothesisOut(number=1, name="Te weinig open afgifte", evidence_for="aanvoer stijgt binnen 2–3 min boven gewenst; modulatie al op minimum bij stop.", missing="zone- en klepstatus niet gekoppeld.", distinguishing_measurement="aantal open vloerverwarmingsgroepen en radiatorkranen tijdens de cycli."),
            HypothesisOut(number=2, name="Beperkte doorstroming ketelcircuit", evidence_for="ketel-ΔT loopt tijdens branden snel op naar 9–11 K.", missing="pompstatus en debiet onbekend.", distinguishing_measurement="pompstatus of debiet; verdeleraanvoer en -retour."),
            HypothesisOut(number=3, name="Minimumvermogen boven actuele warmtevraag", evidence_for="patroon sterker bij buitentemperatuur boven 9 °C.", missing="minimumvermogen in kW niet vastgelegd.", distinguishing_measurement="vergelijk cycli bij lagere buitentemperatuur; leg minimumvermogen vast."),
        ],
        recommendation=RecommendationOut(
            kind=RecommendationKind.CHECK,
            action="Controleer welke circuits werkelijk open staan en of doorstroming beschikbaar is.",
            reason="Onderscheidt hypothese 1 en 2 voordat een instelling wordt gewijzigd.",
            expected_effect="Geen direct energie-effect. Maakt een gerichte vervolgstap mogelijk.",
            comfort_impact="Geen invloed.",
            magnitude="Niet te onderbouwen met huidige gegevens — geen getal genoemd.",
            conditions="Buitentemperatuur ±2 °C van referentie; geen gemarkeerde periode; zelfde thermostaatprogramma.",
            evaluation="Vergelijk korte cycli en comfort 7 dagen na koppelen van zonestatus.",
            success_criterion="Eén hypothese wordt door de nieuwe meting ondersteund of uitgesloten.",
            rollback_criterion="N.v.t. — controle zonder instellingswijziging.",
        ),
        no_advice_text=None,
        bundle=[
            BundledEvidence(text=f"{short}× brander stopt tijdens warmtevraag", source="Stop tijdens vraag · v1.1"),
            BundledEvidence(text="Aanvoer overschrijdt gewenst met 1–4 K vóór stop", source="Temperatuurverloop · v1.0"),
            BundledEvidence(text=f"Mediaan pauze {med_pause} tijdens vraag", source="Pauzeduur · v1.0"),
        ],
        glossary=_glossary("B-014"),
        timeline_range=TimeRange(start=at(0), end=at(GAP[0])),
    )  # fmt: skip
    rollback = RecommendationStatus.ROLLBACK_TRIGGERED
    b011 = FindingDetail(
        id="B-011", category=Category.EFFECT_MEASUREMENT, when_text="sinds 21 sep",
        severity=Severity.MEDIUM, certainty=Certainty.REASONABLE,
        relevance=[Relevance.COMFORT, Relevance.OPERATIONAL_STABILITY],
        rule=RuleRef(id="voor-na", version="1.2"),
        title="Aanvoerverlaging gaf minder korte cycli, maar slechter comfort boven",
        period=TimeRange(start=local(2026, 9, 14), end=local(2026, 9, 29)),
        status=rollback, status_text=status_text(rollback, None),
        evidence=Evidence(
            coverage_pct=97, unknown_s=0, excluded_cycles=0, relevant_cycles=None,
            pattern_cycles=None, repetition_days=7, repetition_window_days=7,
            missing_signals=[_MANIFOLD[0]],
            display=EvidenceDisplay(
                coverage="97 % · beide perioden", cycles="412 voor · 268 na",
                repetition="7 dagen aaneengesloten", missing_signals="Verdeleraanvoer",
            ),
        ),
        observation="Na verlaging van de maximale aanvoer van 70 naar 60 °C daalden de cv-starts per uur van 4,1 naar 2,6. De slaapkamer (vloerverwarming) stond 5,8 u per week meer dan 0,5 °C onder setpoint, tegen 1,2 u ervoor.",
        period_text="14–20 sep vs. 22–28 sep · buiten 11,2 vs. 10,6 °C",
        signals_text="Vlamstatus, aanvoer, kamertemperatuur woonkamer en slaapkamer, buitentemperatuur",
        interpretation="Minder starts is hier geen onverdeelde verbetering. Voldoende temperatuur in de woonkamer bewijst niet dat boven genoeg warmte beschikbaar is. Het ingestelde terugdraaicriterium (4 u/week) is overschreden.",
        hypotheses=[],
        recommendation=RecommendationOut(
            kind=RecommendationKind.REVERT,
            action="Draai de maximale aanvoer terug naar 70 °C.",
            reason="Terugdraaicriterium W-07 bereikt: comfortverlies slaapkamer > 4 u/week.",
            expected_effect="Comfort boven herstelt; korte cycli nemen naar verwachting weer toe.",
            comfort_impact="Positief voor slaapkamer en kinderkamer.",
            magnitude="Terug naar vorige waarde 70 °C.",
            conditions="Leg de wijziging vast; markeer geen andere wijziging in dezelfde week.",
            evaluation="7 dagen, vergelijken met 14–20 sep.",
            follow_up="Overweeg een begeleide proef met 65 °C, met comfortgrens per ruimte.",
            rollback_criterion="N.v.t. — dit is het terugdraaien.",
        ),
        no_advice_text=None, bundle=[], glossary=_glossary("B-011"), timeline_range=None,
    )  # fmt: skip
    b015 = FindingDetail(
        id="B-015", category=Category.DATA_QUALITY, when_text="vandaag 10:10–10:40",
        severity=Severity.MEDIUM, certainty=Certainty.HIGH_MEASURED,
        relevance=[Relevance.DATA_RELIABILITY],
        rule=RuleRef(id="dataverlies", version="1.0"),
        title="CAN-data 30 minuten onderbroken",
        period=TimeRange(start=at(GAP[0]), end=at(GAP[1])),
        status=open_, status_text=status_text(open_, None),
        evidence=Evidence(
            coverage_pct=0, unknown_s=1800, excluded_cycles=0, relevant_cycles=1,
            pattern_cycles=None, repetition_days=1, repetition_window_days=7,
            missing_signals=CAN_SIGNALS,
            display=EvidenceDisplay(
                coverage="0 % in tijdvak", cycles="1 onvolledig",
                repetition="Eerste keer in 7 dagen", missing_signals="9 CAN-entiteiten",
            ),
        ),
        observation="Tussen 10:10 en 10:40 ontving Home Assistant geen updates van de 9 CAN-entiteiten. Home Assistant zelf bleef bereikbaar.",
        period_text="Zo 4 okt 10:10–10:40", signals_text="Alle CAN-signalen",
        interpretation="De cyclus die om 10:05 begon heeft geen bekend einde; de brandduur is onvolledig. De 30 minuten tellen als onbekend, niet als uit-tijd. Na de reconnect is geen kunstmatige branderstart geregistreerd. Het korte-cycli-patroon wordt hierdoor niet als opgelost beschouwd.",
        hypotheses=[], recommendation=None,
        no_advice_text="Geen optimalisatieadvies. Als de onderbreking terugkeert: controleer de CAN-gateway en de verbinding met Home Assistant.",
        bundle=[], glossary=_glossary("B-015"),
        timeline_range=TimeRange(start=at(GAP[0] - 10), end=at(GAP[1] + 10)),
    )  # fmt: skip
    b012 = FindingDetail(
        id="B-012", category=Category.HYDRAULIC, when_text="doorlopend",
        severity=Severity.LOW, certainty=Certainty.INSUFFICIENT_EVIDENCE,
        relevance=[Relevance.COMFORT, Relevance.ENERGY],
        rule=RuleRef(id="hydraulisch", version="0.9"),
        title="Mengverdeler: onvoldoende gegevens voor een hydraulische conclusie",
        period=TimeRange(start=local(2026, 9, 28), end=None),
        status=open_, status_text=status_text(open_, None),
        evidence=Evidence(
            coverage_pct=None, unknown_s=0, excluded_cycles=0, relevant_cycles=None,
            pattern_cycles=None, repetition_days=None, repetition_window_days=None,
            missing_signals=[*_MANIFOLD, _PUMP],
            display=EvidenceDisplay(
                coverage="Verdeler: geen data", cycles="—", repetition="—",
                missing_signals="Verdeleraanvoer, -retour, debiet",
            ),
        ),
        observation="De ketel-ΔT tijdens stabiel cv-bedrijf ligt tussen 4 en 6 K. Meetwaarden van de mengverdeler zijn niet gekoppeld.",
        period_text="28 sep – 4 okt", signals_text="Ketelaanvoer, ketelretour",
        interpretation="Ketel-ΔT zegt niets over de ΔT per vloerverwarmingslus. Zonder verdelerdata wordt geen wijziging aan lusdebiet of mengtemperatuur aanbevolen.",
        hypotheses=[],
        recommendation=RecommendationOut(
            kind=RecommendationKind.MEASUREMENT,
            action="Aanvullende meting: plaats temperatuursensoren op verdeleraanvoer en -retour (boven).",
            reason="Maakt het afgiftecircuit boven los van het ketelcircuit te beoordelen.",
            expected_effect="Hydraulische analyse wordt beschikbaar; ondersteunt ook B-014.",
            magnitude="Geen — er is nog geen instellingsadvies.",
            evaluation="Na 3 dagen data met cv-bedrijf.",
        ),
        no_advice_text=None, bundle=[], glossary=_glossary("B-012"), timeline_range=None,
    )  # fmt: skip
    b016 = FindingDetail(
        id="B-016", category=Category.OPERATING_CONTEXT, when_text="vandaag 07:12",
        severity=Severity.INFO, certainty=Certainty.HIGH, relevance=[],
        rule=RuleRef(id="modus", version="1.1"),
        title="Tapwatercyclus uitgesloten van cv-conclusies",
        period=TimeRange(start=at(72), end=at(86)),
        status=open_, status_text=status_text(open_, None),
        evidence=Evidence(
            coverage_pct=100, unknown_s=0, excluded_cycles=0, relevant_cycles=1,
            pattern_cycles=1, repetition_days=None, repetition_window_days=None,
            missing_signals=[],
            display=EvidenceDisplay(
                coverage="100 %", cycles="1 tapwatercyclus", repetition="—", missing_signals="—"
            ),
        ),
        observation="Om 07:12 brandde de ketel 10 minuten in tapwatermodus met een aanvoer tot 71 °C.",
        period_text="Zo 4 okt 07:12–07:22 + 4 min naloop",
        signals_text="CV-/tapwatermodus, vlamstatus, aanvoer",
        interpretation="Deze cyclus telt niet mee in de korte-cycli-melding en wordt niet gerapporteerd als te hoge cv-aanvoer.",
        hypotheses=[], recommendation=None,
        no_advice_text="Geen advies nodig. Ter informatie zichtbaar gehouden.",
        bundle=[], glossary=_glossary("B-016"),
        timeline_range=TimeRange(start=at(60), end=at(100)),
    )  # fmt: skip
    return [b014, b011, b015, b012, b016]


# --- changes (CHANGES) -----------------------------------------------------------------


def _cond(label: str, before: str, after: str, ok: str) -> ConditionRow:
    comparable = {
        "Ja": Comparability.YES,
        "Beperkt": Comparability.LIMITED,
        "Nee": Comparability.NO,
        "Uitgesloten": Comparability.EXCLUDED,
    }[ok]
    return ConditionRow(label=label, before=before, after=after, comparable=comparable)


def _metric(
    label: str, note: str, before: str, after: str, wv: str, wn: str, effect: str,
    good: bool | None,
) -> MetricComparison:  # fmt: skip
    assessment = (
        MetricAssessment.NEUTRAL
        if good is None
        else MetricAssessment.BETTER
        if good
        else MetricAssessment.WORSE
    )
    return MetricComparison(
        label=label, note=note, before=before, after=after,
        before_bar_pct=float(wv.rstrip("%")), after_bar_pct=float(wn.rstrip("%")),
        effect_text=effect, assessment=assessment,
    )  # fmt: skip


def changes() -> list[Change]:
    return [
        Change(id="W-07", at=local(2026, 9, 21, 8, 30), actor=ChangeActor.USER, parameter="Maximale CV-aanvoer", old_value="70 °C", new_value="60 °C", reason="Aanbeveling B-009 — korte cycli bij lage last", finding_id="B-009", verdict=EvaluationVerdict.TRADE_OFF, verdict_text="Afweging · terugdraaien", rollback_advised=True),
        Change(id="W-06", at=local(2026, 9, 12, 10, 0), actor=ChangeActor.INSTALLER, parameter="Pompstand + maximale aanvoer", old_value="stand 3 · 75 °C", new_value="stand 2 · 70 °C", reason="Onderhoudsbezoek", finding_id=None, verdict=EvaluationVerdict.NOT_ATTRIBUTABLE, verdict_text="Niet toe te schrijven", rollback_advised=False),
        Change(id="W-05", at=local(2026, 9, 1, 21, 0), actor=ChangeActor.USER, parameter="Nachtverlaging eTwist", old_value="18,0 °C", new_value="17,0 °C", reason="Eigen initiatief", finding_id=None, verdict=EvaluationVerdict.INSUFFICIENT_EVIDENCE, verdict_text="Onvoldoende bewijs", rollback_advised=False),
    ]  # fmt: skip


def _days(start: tuple[int, int], end: tuple[int, int]) -> TimeRange:
    """Whole local days ``start`` .. ``end`` (inclusive), as (month, day) pairs."""
    return TimeRange(start=local(2026, *start), end=local(2026, *end) + timedelta(days=1))


def evaluations() -> dict[str, ChangeEvaluation]:
    w07 = ChangeEvaluation(
        change_id="W-07", verdict=EvaluationVerdict.TRADE_OFF, verdict_text="Afweging · terugdraaien",
        summary="Minder starts en langere brandduur, maar comfort boven verslechterde. Het ingestelde terugdraaicriterium (slaapkamer > 4 u/week meer dan 0,5 °C onder setpoint) is overschreden. Dit wordt niet als verbetering beoordeeld.",
        before=_days((9, 14), (9, 20)), after=_days((9, 22), (9, 28)),
        before_text="14–20 sep", after_text="22–28 sep",
        conditions=[
            _cond("Buitentemperatuur gem.", "11,2 °C", "10,6 °C", "Ja"),
            _cond("Setpoint woonkamer", "20,5 °C", "20,5 °C", "Ja"),
            _cond("Andere wijzigingen", "—", "—", "Ja"),
            _cond("Gemarkeerde perioden", "vakantie 17–19 sep", "—", "Uitgesloten"),
        ],
        metrics=[
            _metric("CV-starts per uur", "per waargenomen uur", "4,1", "2,6", "82%", "52%", "Beter", True),
            _metric("Mediaan brandduur", "cv-cycli", "3:12", "6:48", "32%", "68%", "Beter", True),
            _metric("Aandeel korte cycli", "< 3 min tijdens vraag", "61 %", "34 %", "61%", "34%", "Beter", True),
            _metric("Gem. aanvoer stabiel bedrijf", "ketel", "58,3 °C", "52,1 °C", "78%", "70%", "Lager", None),
            _metric("Woonkamer onder setpoint", "> 0,5 °C, u/week", "0,4 u", "0,6 u", "7%", "10%", "Gelijk", None),
            _metric("Slaapkamer onder setpoint", "> 0,5 °C, u/week · grens 4 u", "1,2 u", "5,8 u", "20%", "97%", "Slechter", False),
        ],
    )  # fmt: skip
    w06 = ChangeEvaluation(
        change_id="W-06", verdict=EvaluationVerdict.NOT_ATTRIBUTABLE, verdict_text="Niet toe te schrijven",
        summary="Pompstand en maximale aanvoer zijn op hetzelfde moment gewijzigd. De afname in starts wordt aan geen van beide afzonderlijk toegeschreven. Gebruik een begeleid experiment met één wijziging om dit te onderscheiden.",
        before=_days((9, 5), (9, 11)), after=_days((9, 13), (9, 19)),
        before_text="5–11 sep", after_text="13–19 sep",
        conditions=[
            _cond("Buitentemperatuur gem.", "14,9 °C", "12,7 °C", "Beperkt"),
            _cond("Andere wijzigingen", "—", "2 tegelijk", "Nee"),
            _cond("Gemarkeerde perioden", "—", "vakantie 17–19 sep", "Uitgesloten"),
        ],
        metrics=[
            _metric("CV-starts per uur", "gecombineerd effect", "5,0", "4,1", "100%", "82%", "Niet toe te schrijven", None),
            _metric("Mediaan brandduur", "gecombineerd effect", "2:40", "3:12", "27%", "32%", "Niet toe te schrijven", None),
        ],
    )  # fmt: skip
    w05 = ChangeEvaluation(
        change_id="W-05", verdict=EvaluationVerdict.INSUFFICIENT_EVIDENCE, verdict_text="Onvoldoende bewijs",
        summary="De buitentemperatuur na de wijziging lag gemiddeld 4,6 °C hoger. De perioden zijn niet vergelijkbaar genoeg; er wordt geen effect gerapporteerd. Evaluatie wordt hervat bij vergelijkbaar weer.",
        before=_days((8, 25), (8, 31)), after=_days((9, 2), (9, 8)),
        before_text="25–31 aug", after_text="2–8 sep",
        conditions=[
            _cond("Buitentemperatuur gem.", "13,1 °C", "17,7 °C", "Nee"),
            _cond("Opstookprotocol", "tot 27 aug", "—", "Uitgesloten"),
        ],
        metrics=[],
    )  # fmt: skip
    return {e.change_id: e for e in (w07, w06, w05)}


# --- history (HISTORY) -----------------------------------------------------------------


def history() -> list[HistoryEntry]:
    done, rejected = RecommendationStatus.DONE, RecommendationStatus.REJECTED
    return [
        HistoryEntry(id="H-004", recorded_at=local(2026, 9, 29), recommendation="Max. aanvoer terug naar 70 °C", finding_id="B-011", observation_period=_days((9, 22), (9, 28)), settings_text="Max aanvoer 60 °C · pomp 2", rule=RuleRef(id="voor-na", version="1.2"), status=RecommendationStatus.OPEN, outcome=RecommendationOutcome.PENDING, status_text="Open", reasoning="Comfortverlies slaapkamer 5,8 u/week overschreed het terugdraaicriterium van 4 u/week bij vergelijkbaar weer (11,2 vs 10,6 °C).", note=None, rule_now_text="Ongewijzigd sinds vastleggen."),
        HistoryEntry(id="H-003", recorded_at=local(2026, 9, 13), recommendation="Verlaag max. aanvoer naar 60 °C", finding_id="B-009", observation_period=_days((9, 5), (9, 11)), settings_text="Max aanvoer 70 °C · pomp 2", rule=RuleRef(id="kort-branden", version="1.2"), status=done, outcome=RecommendationOutcome.UNFAVOURABLE, status_text="Uitgevoerd · ongunstig", reasoning="61 % korte cycli tijdens vraag bij buitentemperatuur 12–16 °C. Hypothese minimumvermogen; comfortgegevens boven waren toen beschikbaar maar niet als voorwaarde opgenomen.", note="Uitgevoerd 21 sep na vakantie.", rule_now_text="Regel kort-branden is sinds v1.3 (24 sep) aangescherpt: kortecyclusgrens 4 → 3 min, en een aanvoerverlaging wordt alleen nog voorgesteld met een comfortgrens per ruimte."),
        HistoryEntry(id="H-002", recorded_at=local(2026, 9, 2), recommendation="Koppel slaapkamersensor", finding_id="B-007", observation_period=TimeRange(start=local(2026, 8, 28), end=local(2026, 9, 2)), settings_text="—", rule=RuleRef(id="dekking", version="1.0"), status=done, outcome=RecommendationOutcome.SUCCEEDED, status_text="Uitgevoerd · geslaagd", reasoning="Comfortanalyse boven was niet beschikbaar; vloerverwarmingsruimtes hadden geen eigen temperatuurmeting.", note="Zigbee-sensor geplaatst.", rule_now_text="Ongewijzigd."),
        HistoryEntry(id="H-001", recorded_at=local(2026, 8, 28), recommendation="Pompstand verlagen", finding_id="B-005", observation_period=None, settings_text="pomp 3", rule=RuleRef(id="hydraulisch", version="0.8"), status=rejected, outcome=RecommendationOutcome.PENDING, status_text="Afgewezen", reasoning="Lage ketel-ΔT tijdens opstookprotocol.", note="Opstookprotocol liep nog; advies niet relevant.", rule_now_text="Sinds v0.9 worden gemarkeerde opstookperioden uitgesloten; dit advies zou nu niet meer verschijnen."),
    ]  # fmt: skip


# --- special periods, installation -----------------------------------------------------


def periods() -> list[SpecialPeriod]:
    created = local(2026, 9, 20, 12, 0)
    return [
        SpecialPeriod(id="P-001", kind=SpecialPeriodKind.COMMISSIONING, start=local(2026, 8, 14), end=local(2026, 8, 28), description="Nieuwe dekvloer boven", excluded_from=PeriodExclusions(), created_at=created),
        SpecialPeriod(id="P-002", kind=SpecialPeriodKind.MAINTENANCE, start=local(2026, 9, 2, 9, 0), end=local(2026, 9, 2, 11, 30), description="Jaarlijks onderhoud", excluded_from=PeriodExclusions(), created_at=created),
        SpecialPeriod(id="P-003", kind=SpecialPeriodKind.VACATION, start=local(2026, 9, 17), end=local(2026, 9, 20), description="Thermostaat op 15 °C", excluded_from=PeriodExclusions(), created_at=created),
    ]  # fmt: skip


def installation() -> InstallationProfile:
    return InstallationProfile(
        revision=1,
        updated_at=local(2026, 9, 21, 8, 30),
        summary="Radiatoren beneden, vloerverwarming boven",
        boiler=BoilerInfo(model="Remeha Calenta Ace", control="eTwist, modulerend", data_source="CAN-bus → Home Assistant", heat_demand_source="eTwist in de woonkamer"),
        circuits=[
            Circuit(id="beneden", name="Beneden", kind=CircuitKind.DIRECT, emitter=EmitterType.RADIATOR, rooms=["woonkamer", "keuken", "hal"], note="Radiatoren hangen direct aan de ketel, dus ketelaanvoer en -retour zijn hier representatief."),
            Circuit(id="boven", name="Boven", kind=CircuitKind.MIXING_MANIFOLD, emitter=EmitterType.UNDERFLOOR, loops=5, rooms=["slaapkamer", "kinderkamer", "badkamer"], note="De mengverdeler mengt heet ketelwater met retourwater tot een lagere vloertemperatuur. Ketelmetingen zeggen daarom weinig over de vloer; zonder verdelersensoren geen advies per groep."),
        ],
        zones=[
            Zone(key="beneden", name="Beneden", circuit_key="beneden"),
            Zone(key="boven", name="Boven", circuit_key="boven"),
        ],
        rooms=[
            Room(key="woonkamer", name="Woonkamer", has_sensor=True, is_thermostat=True, schedule_text="07:00–22:30", setpoint=20.5, night_setpoint=17.0, comfort=RoomComfort(status="scheduled", windows=[RoomComfortWindow(weekdays=[0, 1, 2, 3, 4, 5, 6], start_time="07:00", end_time="22:30", target_temperature_c=20.5), RoomComfortWindow(kind="night", weekdays=[0, 1, 2, 3, 4, 5, 6], start_time="22:30", end_time="07:00", target_temperature_c=17.0)])),
            Room(key="keuken", name="Keuken", has_sensor=False, is_thermostat=False, schedule_text=None, setpoint=None, night_setpoint=None),
            Room(key="hal", name="Hal", has_sensor=False, is_thermostat=False, schedule_text=None, setpoint=None, night_setpoint=None),
            Room(key="slaapkamer", name="Slaapkamer", has_sensor=True, is_thermostat=False, schedule_text="21:00–07:30", setpoint=18.0, night_setpoint=None),
            Room(key="kinderkamer", name="Kinderkamer", has_sensor=False, is_thermostat=False, schedule_text="19:00–07:30", setpoint=19.0, night_setpoint=None),
            Room(key="badkamer", name="Badkamer", has_sensor=False, is_thermostat=False, schedule_text="06:30–08:00", setpoint=21.0, night_setpoint=18.0),
        ],
        specifications=[
            Specification(key="max_ch_flow_temperature", label="Maximale CV-aanvoer", status=SpecStatus.KNOWN, value=60, unit="°C", note="sinds 21 sep (W-07)", since=local(2026, 9, 21, 8, 30), change_id="W-07"),
            Specification(key="max_ch_power", label="Maximaal CV-vermogen", status=SpecStatus.UNKNOWN, value=None, unit="kW", note="nog niet ingevuld"),
            Specification(key="min_power", label="Minimumvermogen", status=SpecStatus.UNKNOWN, value=None, unit="kW", note="helpt bij B-014"),
            Specification(key="pump_setting", label="Pompstand", status=SpecStatus.KNOWN, value="Stand 2", unit=None, note="sinds 12 sep (W-06)", since=local(2026, 9, 12, 10, 0), change_id="W-06"),
            Specification(key="modulation_to_kw", label="Modulatie → kW", status=SpecStatus.UNKNOWN, value=None, unit=None, note="geen gecontroleerde omrekening"),
            Specification(key="gas_price", label="Gasprijs", status=SpecStatus.UNKNOWN, value=None, unit="€/m³", note="besparing in euro niet beschikbaar"),
        ],
    )  # fmt: skip


# --- timeline and cycles (buildSim) ----------------------------------------------------

_SIM_MODE = {
    "cv": Mode.CH,
    "tw": Mode.DHW,
    "naloop": Mode.AFTERRUN,
    "onbekend": Mode.UNKNOWN,
    "standby": Mode.STANDBY,
}
_END = {
    "stop": EndReason.STOP_DURING_DEMAND,
    "vraag": EndReason.DEMAND_ENDED,
    "tapwater": EndReason.DHW_ENDED,
    "onvolledig": EndReason.DATA_GAP,
}


def _cycle(c: SimCycle) -> Cycle:
    incomplete = c.end == "onvolledig"
    if c.kort:
        cls = CycleClass.SHORT
    elif c.mode == "tw":
        cls = CycleClass.EXCLUDED
    elif incomplete:
        cls = CycleClass.INCOMPLETE
    else:
        cls = CycleClass.NORMAL
    return Cycle(
        number=c.n,
        start=at(c.s),
        end=None if incomplete else at(c.e),
        duration_s=c.d * 60,
        duration_is_lower_bound=incomplete,
        mode=_SIM_MODE[c.mode],
        end_reason=_END[c.end],
        max_flow_temperature=round(c.max_t, 2),
        flow_setpoint=c.gew,
        mean_modulation_pct=float(js_round(c.mod)) if c.mod else None,
        short_during_demand=c.kort,
        classification=cls,
    )


def cycles() -> list[Cycle]:
    return [_cycle(c) for c in build_sim().cycles]


def cycle_summary() -> CycleSummary:
    st = build_sim().stats
    return CycleSummary(
        observed_hours=st.observed_hours,
        starts_per_hour=round(st.starts_per_hour, 2),
        ch_cycles=st.ch_cycles,
        dhw_cycles=st.dhw_cycles,
        short_during_demand=st.short_cycles,
        short_cycle_threshold_s=SHORT_CYCLE_THRESHOLD_S,
        median_burn_s=st.median_burn_min * 60,
        mean_burn_s=round(st.mean_burn_min * 60, 1),
        median_pause_s=st.median_pause_min * 60,
        total_burn_s=st.total_burn_min * 60,
        incomplete_cycles=1,
    )


def series() -> SampledSeries:
    pts = build_sim().points

    def col(name: str) -> list[float | None]:
        out: list[float | None] = []
        for p in pts:
            value = None if p is None else getattr(p, name)
            out.append(None if value is None else round(value, 2))
        return out

    return SampledSeries(
        start=at(0),
        step_s=30,
        flow_temperature=col("t"),
        return_temperature=col("r"),
        flow_setpoint=col("gew"),
        modulation_pct=col("mod"),
    )


def mode_segments() -> list[ModeSegment]:
    return [ModeSegment(start=at(s.s), end=at(s.e), mode=_SIM_MODE[s.m]) for s in build_sim().modes]


def demand_segments() -> list[DemandSegment]:
    return [
        DemandSegment(start=at(0), end=at(GAP[0]), heat_demand=TriState.YES),
        DemandSegment(start=at(GAP[0]), end=at(GAP[1]), heat_demand=TriState.UNKNOWN),
        DemandSegment(start=at(GAP[1]), end=at(320), heat_demand=TriState.YES),
        DemandSegment(start=at(320), end=at(END_MINUTE), heat_demand=TriState.NO),
    ]


# --- quality (coverage, events, modeShare) ---------------------------------------------

QUALITY_RANGE = TimeRange(start=local(2026, 9, 28, 12), end=local(2026, 10, 4, 12))


def _segment(start_frac: float, width_h: float, kind: CoverageSegmentKind) -> CoverageSegment:
    """v3 positions bars as a fraction of the 7-day window; ported as is."""
    assert QUALITY_RANGE.end is not None
    begin = QUALITY_RANGE.start + timedelta(hours=start_frac * 168)
    end = min(begin + timedelta(hours=width_h), QUALITY_RANGE.end)
    return CoverageSegment(start=begin, end=end, kind=kind)


def coverage() -> list[SignalCoverage]:
    lost = CoverageSegmentKind.CONNECTION_LOST
    stale = CoverageSegmentKind.STALE
    can = [
        CoverageSegment(start=at(GAP[0]), end=at(GAP[1]), kind=lost),
        _segment(2.6 / 7, 0.4, lost),
    ]
    missing = [
        CoverageSegment(start=QUALITY_RANGE.start, end=QUALITY_RANGE.end or NOW, kind=CoverageSegmentKind.NOT_MAPPED)
    ]  # fmt: skip
    room = signal_id(Role.ROOM_TEMPERATURE, "woonkamer")
    bedroom = signal_id(Role.ROOM_TEMPERATURE, "slaapkamer")
    return [
        SignalCoverage(name="Vlamstatus", signal_ids=[FLAME], coverage_pct=99.3, segments=can),
        SignalCoverage(name="Ketelaanvoer / -retour", signal_ids=CAN_SIGNALS[3:5], coverage_pct=99.3, segments=can),
        SignalCoverage(name="Modulatie", signal_ids=[CAN_SIGNALS[5]], coverage_pct=99.3, segments=can),
        SignalCoverage(name="Woonkamer", signal_ids=[room], coverage_pct=100, segments=[]),
        SignalCoverage(name="Slaapkamer", signal_ids=[bedroom], coverage_pct=98.1, segments=[
            _segment(5.42 / 7, 0.6, stale), _segment(1.9 / 7, 2, stale), _segment(0.997, 0.5, stale),
        ]),
        SignalCoverage(name="Buitentemperatuur", signal_ids=[signal_id(Role.OUTDOOR_TEMPERATURE)], coverage_pct=100, segments=[]),
        SignalCoverage(name="Verdeler boven", signal_ids=_MANIFOLD, coverage_pct=None, segments=missing),
        SignalCoverage(name="Gasverbruik", signal_ids=[_GAS], coverage_pct=None, segments=missing),
    ]  # fmt: skip


def quality_events() -> list[QualityEvent]:
    bedroom = signal_id(Role.ROOM_TEMPERATURE, "slaapkamer")
    return [
        QualityEvent(kind=QualityEventKind.CONNECTION_LOST, title="CAN-verbinding verbroken (30 min)", consequence="Tijdvak als onbekend gemarkeerd; cyclus van 10:05 onvolledig", at=at(GAP[0]), end=at(GAP[1]), signal_ids=CAN_SIGNALS),
        QualityEvent(kind=None, recovered=True, title="CAN-verbinding hersteld", consequence="Geen kunstmatige branderstart geregistreerd", at=at(GAP[1]), signal_ids=CAN_SIGNALS),
        QualityEvent(kind=QualityEventKind.STALE, title="Slaapkamersensor 38 min te oud", consequence="Niet gecombineerd met nieuwere ketelwaarden", at=local(2026, 10, 3, 22, 14), signal_ids=[bedroom]),
        QualityEvent(kind=QualityEventKind.DUPLICATE, title="18 dubbele metingen modulatie", consequence="Ontdubbeld", at=local(2026, 10, 1, 3, 0), signal_ids=[CAN_SIGNALS[5]]),
        QualityEvent(kind=QualityEventKind.IMPLAUSIBLE, title="Retour 112 °C — onwaarschijnlijk", consequence="Waarde genegeerd", at=local(2026, 9, 30, 14, 22), signal_ids=[CAN_SIGNALS[4]]),
    ]  # fmt: skip


def mode_share() -> list[ModeShare]:
    rows = [
        (Mode.CH, "Verwarmen (CV)", 276),
        (Mode.DHW, "Tapwater", 10),
        (Mode.AFTERRUN, "Naloop (pomp draait na)", 4),
        (Mode.STANDBY, "Standby", 40),
        (Mode.UNKNOWN, "Onbekend", 30),
    ]
    return [
        ModeShare(mode=m, label=label, minutes=mins, share_pct=round(mins / 360 * 100, 1))
        for m, label, mins in rows
    ]


# --- overview (kpis, status card, data quality) ----------------------------------------

KEX = {
    "Aanvoer": "Temperatuur van het water van de ketel naar radiatoren en vloer.",
    "Retour": "Temperatuur van het water terug naar de ketel. Lager = meer warmte afgegeven.",
    "Modulatie": "Brandervermogen als % van het maximum.",
    "Woonkamer": "Gemeten door de eTwist; deze bepaalt de warmtevraag.",
    "Slaapkamer": "Losse sensor; stuurt de ketel niet aan.",
    "Buiten": "Gebruikt om perioden met vergelijkbaar weer te vergelijken.",
}


def kpis() -> list[LiveValue]:
    last = build_sim().points[-1]
    assert last is not None
    rows = [
        ("flow_temperature", CAN_SIGNALS[3], "Aanvoer", round(last.t, 1), "°C", "gemeten · 4 s", False),
        ("return_temperature", CAN_SIGNALS[4], "Retour", round(last.r, 1), "°C", "gemeten · 4 s", False),
        ("modulation", CAN_SIGNALS[5], "Modulatie", 0.0, "%", "niet omgerekend naar kW", False),
        ("room:woonkamer", signal_id(Role.ROOM_TEMPERATURE, "woonkamer"), "Woonkamer", 20.4, "°C", "doel 20,5 °C", False),
        ("room:slaapkamer", signal_id(Role.ROOM_TEMPERATURE, "slaapkamer"), "Slaapkamer", 17.6, "°C", "doel 18,0 · 14 min oud", True),
        ("outdoor_temperature", signal_id(Role.OUTDOOR_TEMPERATURE), "Buiten", 9.8, "°C", "gemeten · 5 min", False),
    ]  # fmt: skip
    return [
        LiveValue(key=k, signal_id=s, label=lbl, value=v, unit=u, note_text=n,
                  explanation=KEX[lbl], stale=stale)
        for k, s, lbl, v, u, n, stale in rows
    ]  # fmt: skip


def status_card() -> StatusCard:
    return StatusCard(
        mode=Mode.STANDBY,
        title="Standby — geen warmtevraag sinds 11:20",
        text="Vanochtend stopte de brander vaak binnen 3 minuten terwijl er nog warmte gevraagd werd. Dat heet pendelen en is meestal ongunstig voor rendement en slijtage.",
    )  # fmt: skip


def next_action() -> NextAction:
    return NextAction(
        kind="recommendation",
        title="Max. aanvoertemperatuur terug naar 70 °C",
        text="Sinds de verlaging naar 60 °C (21 sep) zat de slaapkamer 5,8 u/week meer dan 0,5 °C onder het setpoint. Je ingestelde grens was 4 u/week, dus het terugdraaicriterium is bereikt.",
        finding_id="B-011",
        action=Action(label="Open advies", target="/bevindingen/B-011"),
    )  # fmt: skip


TODAY_COVERAGE_PCT = round(330 / 360 * 100, 1)
"""91.7 %: six hours with 30 minutes of CAN outage."""


def assessment() -> Assessment:
    """v3 shows 'Datakwaliteit: beperkt': judged, but limited (aanvullingen §5c)."""
    return Assessment(
        level=AssessmentLevel.LIMITED,
        reasons=[
            AssessmentReason(code=AssessmentReasonCode.DATA_GAP, text="30 min CAN-uitval vandaag (10:10–10:40).", action=Action(label="Details", target="/kwaliteit")),
            AssessmentReason(code=AssessmentReasonCode.STALE_SIGNAL, text="Slaapkamersensor 14 min oud.", action=Action(label="Signalen", target="/signalen")),
            AssessmentReason(code=AssessmentReasonCode.SIGNALS_NOT_MAPPED, text="6 signalen nog niet gekoppeld.", action=Action(label="Koppelen", target="/signalen")),
        ],
        observed_hours=round(168 * 0.968, 1),
        minimum_hours=6,
        coverage_pct=96.8,
    )  # fmt: skip


def data_quality() -> DataQualityOverview:
    return DataQualityOverview(
        coverage_pct=TODAY_COVERAGE_PCT,
        level=AssessmentLevel.LIMITED,
        text="Beperkt. 92 % dekking vandaag: 30 min CAN-uitval en 6 signalen nog niet gekoppeld. Conclusies over dat tijdvak worden als onvolledig gemarkeerd.",
        issues=[
            DataQualityIssue(title="CAN-uitval", value_text="10:10–10:40", severity="high"),
            DataQualityIssue(title="Slaapkamersensor verouderd", value_text="14 min", severity="medium"),
            DataQualityIssue(title="Signalen niet gekoppeld", value_text="6", severity="info"),
        ],
    )  # fmt: skip


# --- notifications, HA export, import --------------------------------------------------


def notification_policy() -> NotificationPolicy:
    return NotificationPolicy(
        channels=SeverityChannels(
            high=NotificationChannel.DIRECT,
            medium=NotificationChannel.DAILY_DIGEST,
            low=NotificationChannel.WEEKLY_REPORT,
            info=NotificationChannel.NONE,
        ),
        bundle_related=True,
        renotify_on_worsening=True,
        recovery_text="3 dagen zonder patroon, bij vergelijkbaar weer en ≥ 90 % gegevens",
    )


def notifications() -> list[Notification]:
    st = build_sim().stats
    return [
        Notification(id="N-003", kind=NotificationKind.FINDING_NEW, title="Korte cycli", detail=f"één melding voor {st.short_cycles} cycli", finding_id="B-014", sent_at=local(2026, 10, 4, 9, 15), channel=NotificationChannel.DIRECT, status=DeliveryStatus.SENT),
        Notification(id="N-002", kind=NotificationKind.FINDING_NEW, title="CAN-uitval", detail="30 minuten", finding_id="B-015", sent_at=local(2026, 10, 4, 10, 41), channel=NotificationChannel.DAILY_DIGEST, status=DeliveryStatus.SENT),
        Notification(id="N-001", kind=NotificationKind.FINDING_WORSENED, title="Terugzetten aanbevolen", detail="aanvoer", finding_id="B-011", sent_at=local(2026, 9, 29, 8, 0), channel=NotificationChannel.DAILY_DIGEST, status=DeliveryStatus.SENT),
    ]  # fmt: skip


def ha_export(open_findings: int) -> list[HaExportEntity]:
    st = build_sim().stats
    per_hour = round(st.starts_per_hour, 1)
    return [
        HaExportEntity(entity_id="sensor.cv_analyse_starts_per_uur", state=f"{per_hour}", display=nl(st.starts_per_hour), unit="1/h"),
        HaExportEntity(entity_id="sensor.cv_analyse_korte_cycli_6u", state=str(st.short_cycles), display=str(st.short_cycles)),
        HaExportEntity(entity_id="sensor.cv_analyse_gegevensdekking", state=str(TODAY_COVERAGE_PCT), display=f"{nl(TODAY_COVERAGE_PCT)} %", unit="%"),
        HaExportEntity(entity_id="sensor.cv_analyse_open_bevindingen", state=str(open_findings), display=str(open_findings)),
        HaExportEntity(entity_id="sensor.cv_analyse_hoogste_ernst", state="hoog", display="hoog"),
        HaExportEntity(entity_id="sensor.cv_analyse_volgende_actie", state="B-011", display="B-011"),
        # §5c: level 'limited' is not insufficient data, so the binary sensor is off.
        HaExportEntity(entity_id="binary_sensor.cv_analyse_onvoldoende_gegevens", state="off", display="uit"),
    ]  # fmt: skip


EARLIEST_AVAILABLE = local(2026, 9, 24)


def finished_import() -> ImportJob:
    signal_rows = [s for s in signals() if s.entity_id]
    return ImportJob(
        id="I-001",
        status=ImportStatus.DONE,
        range=TimeRange(start=EARLIEST_AVAILABLE, end=local(2026, 10, 4, 9, 12)),
        blocks_done=10,
        blocks_total=10,
        current_block_day=None,
        observations_imported=141_880,
        duplicates_skipped=1_304,
        signals=[
            ImportSignalProgress(
                signal_id=s.id,
                observations=141_880 // len(signal_rows),
                first_at=local(2026, 10, 2) if "slaapkamer" in s.id else EARLIEST_AVAILABLE,
            )
            for s in signal_rows
        ],
        earliest_available_at=EARLIEST_AVAILABLE,
        cycles_found=1_212,
        coverage_pct=97.4,
        warnings=[
            "Slaapkamer: historie begint pas op 2 okt (sensor later toegevoegd).",
            "27 sep 03:10–05:40: geen gegevens van 9 CAN-signalen (telt als onbekend).",
        ],
        errors=[],
        started_at=local(2026, 10, 4, 9, 12),
        finished_at=local(2026, 10, 4, 9, 16),
    )


def import_days(start: datetime, end: datetime) -> list[date]:
    """Local calendar days covered by an import (one block per day)."""
    first, last = start.astimezone(AMS).date(), end.astimezone(AMS).date()
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]
