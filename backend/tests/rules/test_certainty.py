"""Certainty categories and their derivation from the criteria template (ADR-004 §5)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cvidee.analysis.types import Role
from cvidee.rules.base import (
    Certainty,
    CertaintyCriteria,
    EvidenceSummary,
    Thresholds,
    signal_ref,
)
from cvidee.rules.certainty import CertaintyReason, derive_certainty

# Shaped like kort-branden: min 6 relevant cycles and 80 % coverage, structural on 2 of
# 7 days, reasonable from 12 cycles / 90 % / 3 days, high from 30 cycles / 95 % / 5 days.
CRITERIA = CertaintyCriteria(
    minimum=Thresholds(coverage=0.8, relevant_cycles=6),
    structural_repetition_days=2,
    repetition_window_days=7,
    reasonable=Thresholds(coverage=0.9, relevant_cycles=12, repetition_days=3),
    high=Thresholds(coverage=0.95, relevant_cycles=30, repetition_days=5),
)


def evidence(
    coverage: float = 0.97,
    cycles: int | None = 40,
    days: int | None = 6,
    missing: bool = False,
) -> EvidenceSummary:
    return EvidenceSummary(
        coverage=coverage,
        relevant_cycles=cycles,
        pattern_cycles=cycles,
        repetition_days=days,
        repetition_window_days=7,
        missing_signals=(signal_ref(Role.PUMP_STATE),) if missing else (),
    )


def test_order_and_lowering() -> None:
    assert [c.rank for c in Certainty] == list(range(6))
    assert Certainty.HIGH.lowered() is Certainty.REASONABLE
    assert Certainty.MODERATE.lowered(floor=Certainty.MODERATE) is Certainty.MODERATE
    assert Certainty.PROVISIONAL.lowered(floor=Certainty.MODERATE) is Certainty.PROVISIONAL
    assert Certainty.INSUFFICIENT_EVIDENCE.lowered() is Certainty.INSUFFICIENT_EVIDENCE
    assert Certainty.HIGH_MEASURED.at_most(Certainty.REASONABLE) is Certainty.REASONABLE


@pytest.mark.parametrize(
    ("ev", "reason"),
    [
        (evidence(coverage=0.79), CertaintyReason.BELOW_MIN_COVERAGE),
        (evidence(cycles=5), CertaintyReason.BELOW_MIN_CYCLES),
        (evidence(cycles=None), CertaintyReason.BELOW_MIN_CYCLES),
    ],
)
def test_below_minimum_is_insufficient_evidence(ev: EvidenceSummary, reason: str) -> None:
    result = derive_certainty(ev, CRITERIA)
    assert result.certainty is Certainty.INSUFFICIENT_EVIDENCE
    assert reason in result.reasons


def test_not_repeated_over_days_is_provisional() -> None:
    """FR-22: a conclusion on little data is shown as provisional."""
    result = derive_certainty(evidence(days=1), CRITERIA)
    assert result.certainty is Certainty.PROVISIONAL
    assert result.reasons == (CertaintyReason.NOT_STRUCTURAL,)
    assert derive_certainty(evidence(days=None), CRITERIA).certainty is Certainty.PROVISIONAL


def test_levels() -> None:
    assert derive_certainty(evidence(cycles=8, days=2), CRITERIA).certainty is Certainty.MODERATE
    assert derive_certainty(evidence(cycles=20, days=3), CRITERIA).certainty is Certainty.REASONABLE
    assert derive_certainty(evidence(cycles=40, days=6), CRITERIA).certainty is Certainty.HIGH


def test_missing_signals_lower_one_step_but_not_below_moderate() -> None:
    lowered = derive_certainty(evidence(cycles=40, days=6, missing=True), CRITERIA)
    assert lowered.certainty is Certainty.REASONABLE
    assert CertaintyReason.LOWERED_FOR_MISSING_SIGNALS in lowered.reasons
    floor = derive_certainty(evidence(cycles=8, days=2, missing=True), CRITERIA)
    assert floor.certainty is Certainty.MODERATE
    assert CertaintyReason.LOWERED_FOR_MISSING_SIGNALS not in floor.reasons


def test_design_b014_is_moderate() -> None:
    """B-014: 93 % coverage, 24 relevant cycles, 3 of 7 days, zone/manifold/pump missing →
    reasonable lowered one step → "Matig"."""
    ev = EvidenceSummary(
        coverage=0.93,
        relevant_cycles=24,
        pattern_cycles=18,
        repetition_days=3,
        repetition_window_days=7,
        missing_signals=(signal_ref(Role.PUMP_STATE),),
    )
    assert derive_certainty(ev, CRITERIA).certainty is Certainty.MODERATE


def test_measured_only_when_allowed() -> None:
    """B-015 (dataverlies): direct measurement → "Hoog (gemeten)"."""
    measured = CertaintyCriteria(
        minimum=Thresholds(),
        reasonable=Thresholds(),
        high=Thresholds(),
        allow_measured=True,
    )
    ev = EvidenceSummary(coverage=0.0)
    assert derive_certainty(ev, measured, measured=True).certainty is Certainty.HIGH_MEASURED
    assert derive_certainty(ev, measured).certainty is Certainty.HIGH
    not_allowed = CertaintyCriteria(
        minimum=Thresholds(), reasonable=Thresholds(), high=Thresholds()
    )
    assert derive_certainty(ev, not_allowed, measured=True).certainty is Certainty.HIGH


def test_unreachable_levels_and_cap() -> None:
    only_moderate = CertaintyCriteria(minimum=Thresholds(coverage=0.5))
    assert derive_certainty(evidence(), only_moderate).certainty is Certainty.MODERATE
    capped = CertaintyCriteria(
        minimum=Thresholds(),
        reasonable=Thresholds(),
        high=Thresholds(),
        max_certainty=Certainty.REASONABLE,
    )
    result = derive_certainty(evidence(), capped)
    assert result.certainty is Certainty.REASONABLE
    assert result.reasons[-1] is CertaintyReason.CAPPED


def test_criteria_validation() -> None:
    with pytest.raises(ValueError, match="together"):
        CertaintyCriteria(minimum=Thresholds(), structural_repetition_days=2)
    with pytest.raises(ValueError, match="exceed"):
        CertaintyCriteria(
            minimum=Thresholds(), structural_repetition_days=8, repetition_window_days=7
        )
    with pytest.raises(ValueError, match="requires"):
        CertaintyCriteria(minimum=Thresholds(), high=Thresholds())


@given(
    coverage=st.floats(0.0, 1.0),
    extra_coverage=st.floats(0.0, 1.0),
    cycles=st.integers(0, 60),
    extra_cycles=st.integers(0, 60),
    days=st.integers(0, 7),
    extra_days=st.integers(0, 7),
    missing=st.booleans(),
)
def test_more_evidence_never_lowers_certainty(
    coverage: float,
    extra_coverage: float,
    cycles: int,
    extra_cycles: int,
    days: int,
    extra_days: int,
    missing: bool,
) -> None:
    """Monotonicity: more coverage, cycles or repetition never gives a weaker category."""
    more_days = min(days + extra_days, 7)
    weak = evidence(coverage, cycles, days, missing)
    strong = evidence(
        min(coverage + extra_coverage, 1.0),
        cycles + extra_cycles,
        more_days,
        missing,
    )
    assert (
        derive_certainty(strong, CRITERIA).certainty.rank
        >= derive_certainty(weak, CRITERIA).certainty.rank
    )
