"""Invariants of the rule contract types (ADR-004 §3-§4)."""

from __future__ import annotations

import dataclasses

import pytest

from cvidee.analysis.types import HOUR_MS, MINUTE_MS, Mode, Role, ScopeKind, TimeRange
from cvidee.rules.base import (
    Category,
    Certainty,
    CircuitFacts,
    CircuitKind,
    EvidenceSummary,
    FindingCandidate,
    Hypothesis,
    RecommendationDraft,
    RecommendationKind,
    Relevance,
    RuleContext,
    Severity,
    SpecialPeriod,
    SpecialPeriodKind,
    display_version,
    local_days,
    scope_key_for,
    signal_ref,
)

from .helpers import DAY_MS, PROFILE, T0, cycle

PERIOD = TimeRange(T0, T0 + DAY_MS)


def advice(kind: RecommendationKind, rollback: str | None = None) -> RecommendationDraft:
    return RecommendationDraft(
        kind=kind,
        action="Controleer welke circuits werkelijk open staan.",
        reason="Onderscheidt hypothese 1 en 2.",
        expected_effect="Geen direct energie-effect.",
        comfort_impact="Geen invloed.",
        conditions="Buitentemperatuur ±2 °C van referentie.",
        evaluation="Vergelijk korte cycli 7 dagen na koppelen van zonestatus.",
        success_criterion="Eén hypothese wordt ondersteund of uitgesloten.",
        rollback_criterion=rollback,
    )


def candidate(
    certainty: Certainty = Certainty.MODERATE,
    recommendation: RecommendationDraft | None = None,
    **kwargs: object,
) -> FindingCandidate:
    fields: dict[str, object] = {
        "scope_key": "boiler:ch",
        "category": Category.CYCLES,
        "title": "Herhaald kort branden tijdens aanhoudende warmtevraag",
        "severity": Severity.HIGH,
        "certainty": certainty,
        "relevance": (Relevance.OPERATIONAL_STABILITY, Relevance.ENERGY),
        "observation": "In 18 van 24 cv-cycli stopt de brander binnen 3 minuten.",
        "period": PERIOD,
        "signals": (signal_ref(Role.FLAME),),
        "evidence": EvidenceSummary(coverage=0.93, relevant_cycles=24, pattern_cycles=18),
        "interpretation": "Dit past bij onvoldoende warmteafgifte, maar bewijst de oorzaak niet.",
        "hypotheses": (
            Hypothesis(
                name="Te weinig open afgifte",
                evidence_for="aanvoer stijgt binnen 2 tot 3 min boven gewenst.",
                missing="zone- en klepstatus niet gekoppeld.",
                distinguishing_measurement="aantal open groepen tijdens de cycli.",
                signals_needed=(Role.VALVE_STATE,),
            ),
        ),
        "recommendation": recommendation or advice(RecommendationKind.CHECK),
    }
    fields.update(kwargs)
    return FindingCandidate(**fields)  # type: ignore[arg-type]


def test_valid_candidate_like_b014() -> None:
    c = candidate()
    assert c.recommendation is not None
    assert c.recommendation.magnitude is None  # "niet te onderbouwen": no invented number


def test_setting_change_needs_rollback_criterion() -> None:
    with pytest.raises(ValueError, match="rollback"):
        advice(RecommendationKind.SETTING_CHANGE)
    assert advice(RecommendationKind.SETTING_CHANGE, rollback="Comfort > 4 u/week").kind


@pytest.mark.parametrize("certainty", [Certainty.PROVISIONAL, Certainty.INSUFFICIENT_EVIDENCE])
def test_no_setting_change_on_weak_evidence(certainty: Certainty) -> None:
    change = advice(RecommendationKind.SETTING_CHANGE, rollback="terug naar 70 °C")
    with pytest.raises(ValueError, match=r"setting change|measurement"):
        candidate(certainty, change)


def test_insufficient_evidence_requires_measurement() -> None:
    """FR-28 / scenario 10: propose an additional measurement instead of a diagnosis."""
    with pytest.raises(ValueError, match="measurement"):
        candidate(Certainty.INSUFFICIENT_EVIDENCE, advice(RecommendationKind.CHECK))
    ok = candidate(Certainty.INSUFFICIENT_EVIDENCE, advice(RecommendationKind.MEASUREMENT))
    assert ok.certainty is Certainty.INSUFFICIENT_EVIDENCE


def test_candidate_shape_checks() -> None:
    with pytest.raises(ValueError, match="no-advice"):
        dataclasses.replace(candidate(), recommendation=None)
    no_advice = dataclasses.replace(candidate(), recommendation=None, no_advice_reason="Geen.")
    assert no_advice.recommendation is None
    with pytest.raises(ValueError, match="scope_key"):
        candidate(scope_key="boiler ch")
    with pytest.raises(ValueError, match="supports"):
        candidate(supports=("b", "a"))
    with pytest.raises(ValueError, match="relevance"):
        candidate(relevance=())
    info = candidate(severity=Severity.INFO, relevance=())
    assert info.severity is Severity.INFO


def test_evidence_summary_invariants() -> None:
    with pytest.raises(ValueError, match="coverage"):
        EvidenceSummary(coverage=1.2)
    with pytest.raises(ValueError, match="pattern_cycles"):
        EvidenceSummary(coverage=0.9, relevant_cycles=2, pattern_cycles=3)
    with pytest.raises(ValueError, match="repetition_days"):
        EvidenceSummary(coverage=0.9, repetition_days=8, repetition_window_days=7)
    with pytest.raises(ValueError, match="sorted"):
        EvidenceSummary(
            coverage=0.9,
            missing_signals=(signal_ref(Role.PUMP_STATE), signal_ref(Role.FLOW_RATE)),
        )


def test_relevant_cycles_exclude_dhw_and_special_periods() -> None:
    """Scenario 4 and 9: DHW cycles and marked periods are excluded but stay visible."""
    commissioning = SpecialPeriod(
        TimeRange(T0 + 12 * HOUR_MS, T0 + 14 * HOUR_MS), SpecialPeriodKind.COMMISSIONING
    )
    holiday_visible = SpecialPeriod(
        TimeRange(T0 + 20 * HOUR_MS, T0 + 21 * HOUR_MS), SpecialPeriodKind.HOLIDAY, excluded=False
    )
    cycles = (
        cycle(T0 + 6 * HOUR_MS),
        cycle(T0 + 7 * HOUR_MS + 12 * MINUTE_MS, minutes=10, mode=Mode.DHW),
        cycle(T0 + 13 * HOUR_MS),
        cycle(T0 + 20 * HOUR_MS + 5 * MINUTE_MS),
        cycle(T0 + DAY_MS + HOUR_MS),  # outside the period
    )
    ctx = RuleContext(
        now=T0 + DAY_MS,
        period=PERIOD,
        profile=PROFILE,
        cycles=cycles,
        special_periods=(commissioning, holiday_visible),
    )
    assert [c.start for c in ctx.relevant_cycles()] == [cycles[0].start, cycles[3].start]
    assert [c.start for c in ctx.excluded_cycles()] == [cycles[1].start, cycles[2].start]
    assert ctx.excluded_ranges() == (commissioning.range,)
    both = ctx.relevant_cycles(frozenset({Mode.CH, Mode.DHW}))
    assert cycles[1] in both


def test_local_days_handle_dst() -> None:
    """25 Oct 2026 has 25 hours in Europe/Amsterdam; days are clipped to the range."""
    oct_24 = T0 + 20 * DAY_MS
    days = local_days(TimeRange(oct_24, oct_24 + 3 * DAY_MS))
    assert [d.duration_ms for d in days] == [DAY_MS, DAY_MS + HOUR_MS, DAY_MS - HOUR_MS]
    partial = local_days(TimeRange(T0 + 6 * HOUR_MS, T0 + 30 * HOUR_MS))
    assert [d.duration_ms for d in partial] == [18 * HOUR_MS, 6 * HOUR_MS]


def test_installation_facts() -> None:
    assert PROFILE.has_mixing_manifold
    assert PROFILE.has_direct_circuit
    assert PROFILE.manifolds == ("boven",)
    assert PROFILE.scope_keys(ScopeKind.ROOM) == ("slaapkamer", "woonkamer")
    with pytest.raises(ValueError, match="manifold"):
        CircuitFacts("boven", CircuitKind.MIXING_MANIFOLD)


def test_helpers() -> None:
    assert display_version("1.3.0") == "v1.3"
    assert scope_key_for(ScopeKind.BOILER, None, "ch") == "boiler:ch"
    assert scope_key_for(ScopeKind.ROOM, "slaapkamer") == "room:slaapkamer"
    ref = signal_ref(Role.ROOM_TEMPERATURE, "slaapkamer")
    assert str(ref) == "room_temperature@room:slaapkamer"
