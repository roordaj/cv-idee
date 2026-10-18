"""Availability per analysis and per rule (FR-04, ADR-004 §6)."""

from __future__ import annotations

from cvidee.analysis.types import MINUTE_MS, Role
from cvidee.rules.availability import (
    AvailabilityPolicy,
    SignalRequirement,
    analysis_requirements,
    assess,
    assess_analyses,
)
from cvidee.rules.base import (
    AnalysisId,
    Availability,
    AvailabilityStatus,
    InstallationFacts,
    IssueKind,
    ResolutionLimit,
    SignalStatus,
    signal_ref,
)

from .helpers import PROFILE, boiler_signals, status

AVAILABLE = AvailabilityStatus.AVAILABLE
LIMITED = AvailabilityStatus.LIMITED
UNAVAILABLE = AvailabilityStatus.UNAVAILABLE


def by_analysis(
    signals: tuple[SignalStatus, ...], profile: InstallationFacts = PROFILE
) -> dict[AnalysisId, Availability]:
    return {a.analysis: a.availability for a in assess_analyses(signals, profile)}


def test_table_covers_every_analysis_in_design_order() -> None:
    assert list(analysis_requirements(AvailabilityPolicy())) == list(AnalysisId)
    assert [a.analysis for a in assess_analyses((), PROFILE)] == list(AnalysisId)


def test_no_gas_meter_cycles_available_consumption_unavailable() -> None:
    """FR-04 acceptance: without a gas meter the cycle analyses keep working; the
    consumption analysis reports that gas data is missing."""
    result = by_analysis(boiler_signals())
    assert result[AnalysisId.CYCLES].status is AVAILABLE
    assert result[AnalysisId.TEMPERATURE].status is AVAILABLE
    assert result[AnalysisId.OPERATING_MODE].status is AVAILABLE
    consumption = result[AnalysisId.CONSUMPTION]
    assert consumption.status is UNAVAILABLE
    assert consumption.missing_required == (signal_ref(Role.GAS_CUMULATIVE),)
    assert signal_ref(Role.OUTDOOR_TEMPERATURE) in consumption.missing_signals


def test_efficiency_needs_gas_and_heat_meter() -> None:
    nothing = by_analysis(boiler_signals())[AnalysisId.EFFICIENCY]
    assert nothing.status is UNAVAILABLE
    assert set(nothing.missing_required) == {
        signal_ref(Role.GAS_CUMULATIVE),
        signal_ref(Role.HEAT_METER),
    }

    gas_only = by_analysis((*boiler_signals(), status(Role.GAS_CUMULATIVE)))
    assert gas_only[AnalysisId.EFFICIENCY].status is UNAVAILABLE
    assert gas_only[AnalysisId.EFFICIENCY].missing_required == (signal_ref(Role.HEAT_METER),)
    assert gas_only[AnalysisId.CONSUMPTION].status is LIMITED  # no outdoor temperature

    both = by_analysis((*boiler_signals(), status(Role.GAS_CUMULATIVE), status(Role.HEAT_METER)))
    assert both[AnalysisId.EFFICIENCY].status is AVAILABLE


def test_missing_mode_signal_limits_cycles_and_mode() -> None:
    """FR-09: without a mode signal the classification is inferred (limited certainty)."""
    result = by_analysis(boiler_signals(without=(Role.OPERATING_MODE,)))
    assert result[AnalysisId.CYCLES].status is LIMITED
    assert result[AnalysisId.OPERATING_MODE].status is LIMITED
    assert result[AnalysisId.CYCLES].missing_signals == (signal_ref(Role.OPERATING_MODE),)


def test_heat_demand_or_flow_setpoint_is_enough_for_cycles() -> None:
    no_demand = by_analysis(boiler_signals(without=(Role.HEAT_DEMAND,)))
    assert no_demand[AnalysisId.CYCLES].status is AVAILABLE
    neither = by_analysis(boiler_signals(without=(Role.HEAT_DEMAND, Role.FLOW_SETPOINT)))
    assert neither[AnalysisId.CYCLES].status is LIMITED


def test_flame_resolution() -> None:
    policy = AvailabilityPolicy(desired_flame_resolution_ms=10_000)
    req = analysis_requirements(policy)[AnalysisId.CYCLES]
    base = boiler_signals(without=(Role.FLAME,))
    fine = assess(req, (*base, status(Role.FLAME, resolution_ms=4_000)), PROFILE, policy)
    assert fine.status is AVAILABLE
    coarse = assess(req, (*base, status(Role.FLAME, resolution_ms=30_000)), PROFILE, policy)
    assert coarse.status is LIMITED
    assert [i.kind for i in coarse.issues] == [IssueKind.RESOLUTION]
    unknown = assess(req, (*base, status(Role.FLAME, resolution_ms=None)), PROFILE, policy)
    assert unknown.status is LIMITED
    assert [i.kind for i in unknown.issues] == [IssueKind.RESOLUTION_UNKNOWN]


def test_rule_resolution_limit_can_make_a_rule_unavailable() -> None:
    """Short-cycle detection with a 3 min limit cannot work with a 2 min flame resolution."""
    req = SignalRequirement(
        required=(Role.FLAME,),
        resolution=(
            ResolutionLimit(Role.FLAME, 45_000),
            ResolutionLimit(Role.FLAME, 90_000, AvailabilityStatus.UNAVAILABLE),
        ),
    )
    assert assess(req, (status(Role.FLAME, resolution_ms=60_000),), PROFILE).status is LIMITED
    result = assess(req, (status(Role.FLAME, resolution_ms=2 * MINUTE_MS),), PROFILE)
    assert result.status is UNAVAILABLE


def test_coverage_and_staleness() -> None:
    req = SignalRequirement(required=(Role.FLAME,))
    assert assess(req, (status(Role.FLAME, coverage=0.5),), PROFILE).status is LIMITED
    no_data = assess(req, (status(Role.FLAME, coverage=0.0),), PROFILE)
    assert no_data.status is UNAVAILABLE
    assert no_data.issues[0].kind is IssueKind.NO_DATA
    assert assess(req, (status(Role.FLAME, stale=True),), PROFILE).status is LIMITED


def test_comfort_per_room() -> None:
    """Design v3: comfort is limited when one room's sensor is stale or a room has no
    sensor; unavailable when no room has data or the profile has no rooms."""
    rooms = (
        status(Role.ROOM_TEMPERATURE, "woonkamer"),
        status(Role.ROOM_SETPOINT, "woonkamer"),
        status(Role.ROOM_TEMPERATURE, "slaapkamer", stale=True),
        status(Role.ROOM_SETPOINT, "slaapkamer"),
        status(Role.OUTDOOR_TEMPERATURE),
    )
    assert by_analysis(rooms)[AnalysisId.COMFORT].status is LIMITED
    fresh = (*rooms[:2], status(Role.ROOM_TEMPERATURE, "slaapkamer"), *rooms[3:])
    assert by_analysis(fresh)[AnalysisId.COMFORT].status is AVAILABLE

    with_kinderkamer = InstallationFacts(rooms=("woonkamer", "slaapkamer", "kinderkamer"))
    comfort = by_analysis(fresh, with_kinderkamer)[AnalysisId.COMFORT]
    assert comfort.status is LIMITED
    assert signal_ref(Role.ROOM_TEMPERATURE, "kinderkamer") in comfort.missing_signals

    assert by_analysis(boiler_signals())[AnalysisId.COMFORT].status is UNAVAILABLE
    no_rooms = by_analysis(boiler_signals(), InstallationFacts())[AnalysisId.COMFORT]
    assert no_rooms.status is UNAVAILABLE
    assert {i.kind for i in no_rooms.issues if i.required} == {IssueKind.NO_SCOPE_IN_PROFILE}


def test_hydraulic_without_manifold_data() -> None:
    """Scenario 6: mixed installation without manifold measurements → limited, and the
    note lists every option (manifold flow and return, or a flow rate)."""
    hydraulic = by_analysis(boiler_signals())[AnalysisId.HYDRAULIC]
    assert hydraulic.status is LIMITED
    assert set(hydraulic.missing_signals) == {
        signal_ref(Role.MANIFOLD_FLOW_TEMPERATURE, "boven"),
        signal_ref(Role.MANIFOLD_RETURN_TEMPERATURE, "boven"),
        signal_ref(Role.FLOW_RATE),
        signal_ref(Role.PUMP_STATE),
    }

    manifold = (
        *boiler_signals(),
        status(Role.MANIFOLD_FLOW_TEMPERATURE, "boven"),
        status(Role.MANIFOLD_RETURN_TEMPERATURE, "boven"),
        status(Role.PUMP_STATE),
    )
    assert by_analysis(manifold)[AnalysisId.HYDRAULIC].status is AVAILABLE
    half = (*boiler_signals(), status(Role.MANIFOLD_FLOW_TEMPERATURE, "boven"))
    assert by_analysis(half)[AnalysisId.HYDRAULIC].status is LIMITED


def test_zones_need_demand_or_valve_per_zone() -> None:
    profile = InstallationFacts(zones=("beneden", "boven"))
    assert by_analysis(boiler_signals(), profile)[AnalysisId.ZONES].status is UNAVAILABLE
    some = (*boiler_signals(), status(Role.VALVE_STATE, "boven"))
    assert by_analysis(some, profile)[AnalysisId.ZONES].status is LIMITED
    every = (*some, status(Role.ZONE_DEMAND, "beneden"))
    # Each zone has one of the alternatives, but neither alternative covers all zones.
    assert by_analysis(every, profile)[AnalysisId.ZONES].status is LIMITED
    full = (*every, status(Role.VALVE_STATE, "beneden"))
    assert by_analysis(full, profile)[AnalysisId.ZONES].status is AVAILABLE


def test_assessment_is_order_independent() -> None:
    signals = (*boiler_signals(), status(Role.GAS_CUMULATIVE))
    assert assess_analyses(signals, PROFILE) == assess_analyses(tuple(reversed(signals)), PROFILE)
