"""Zone counts remain scoped by source, cycle and known status (FR-18)."""

from cvidee.analysis.types import (
    BurnerCycle,
    EndReason,
    Mode,
    ObservationKind,
    Provenance,
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
)
from cvidee.analysis.zone_context import Zone, analyze_zone_context

START = 1_800_000_000_000
END = START + 3_600_000
PERIOD = TimeRange(START, END)
PROVENANCE = Provenance(ValueKind.MEASURED, "binary_sensor.zone")


def cycle(start: int, *, mode: Mode = Mode.CH, short: bool = False) -> BurnerCycle:
    duration = 60_000 if short else 600_000
    return BurnerCycle(
        start=start,
        end=start + duration,
        duration_ms=duration,
        complete=True,
        start_observed=True,
        mode=mode,
        end_reason=EndReason.STOP_DURING_DEMAND if short else EndReason.DEMAND_ENDED,
    )


def timeline(role: Role, zone: str | None, value: bool | None) -> SignalTimeline:
    signal = SignalRef(
        role,
        Scope(ScopeKind.ZONE, zone) if zone is not None else Scope(ScopeKind.BOILER),
    )
    interval = (
        UnknownInterval(START, END, UnknownReason.UNAVAILABLE)
        if value is None
        else ValueInterval(
            START,
            END,
            value,
            PROVENANCE,
            START,
            ObservationKind.POLL,
        )
    )
    return SignalTimeline(signal, PERIOD, (interval,))


def test_zone_demand_and_valve_counts_are_separate_and_reuse_short_classification() -> None:
    zones = (Zone("up", "Boven"), Zone("down", "Beneden"))
    heat = timeline(Role.HEAT_DEMAND, None, True)
    result = analyze_zone_context(
        zones,
        (cycle(START, short=True), cycle(START + 1_000_000)),
        {
            "up": timeline(Role.ZONE_DEMAND, "up", True),
            "down": timeline(Role.ZONE_DEMAND, "down", False),
        },
        {
            "up": timeline(Role.VALVE_STATE, "up", True),
            "down": timeline(Role.VALVE_STATE, "down", True),
        },
        heat,
        PERIOD,
        180_000,
        few_active_zones_max=1,
    )

    assert result.zone_demand.distribution[0].active_count == 1
    assert result.zone_demand.distribution[0].cycles == 2
    assert result.zone_demand.distribution[0].short_cycles == 1
    assert result.valve_state.distribution[0].active_count == 2
    assert result.zone_demand.coverage == result.valve_state.coverage == 1
    assert result.few_active_zones_max == 1


def test_only_one_source_can_be_available_without_filling_the_other_with_zeros() -> None:
    zones = (Zone("up", "Boven"),)
    result = analyze_zone_context(
        zones,
        (cycle(START),),
        {"up": timeline(Role.ZONE_DEMAND, "up", True)},
        {},
        timeline(Role.HEAT_DEMAND, None, True),
        PERIOD,
        180_000,
    )

    assert result.zone_demand.availability == "available"
    assert result.valve_state.availability == "not_available"
    assert result.valve_state.distribution == ()
    assert result.valve_state.unmapped_zone_keys == ("up",)


def test_only_valve_source_can_report_a_known_zero_active_count() -> None:
    zones = (Zone("up", "Boven"),)
    result = analyze_zone_context(
        zones,
        (cycle(START),),
        {},
        {"up": timeline(Role.VALVE_STATE, "up", False)},
        timeline(Role.HEAT_DEMAND, None, True),
        PERIOD,
        180_000,
    )

    assert result.valve_state.availability == "available"
    assert result.valve_state.distribution[0].active_count == 0
    assert result.zone_demand.availability == "not_available"
    assert result.zone_demand.distribution == ()


def test_unknown_zone_status_is_incomplete_and_dhw_or_unknown_heat_demand_is_excluded() -> None:
    zones = (Zone("up", "Boven"), Zone("down", "Beneden"))
    demand = {
        "up": timeline(Role.ZONE_DEMAND, "up", True),
        "down": timeline(Role.ZONE_DEMAND, "down", None),
    }
    result = analyze_zone_context(
        zones,
        (cycle(START, short=True), cycle(START + 1_000_000, mode=Mode.DHW)),
        demand,
        {},
        timeline(Role.HEAT_DEMAND, None, True),
        PERIOD,
        180_000,
    )

    assert result.zone_demand.availability == "limited"
    assert result.zone_demand.distribution == ()
    assert result.zone_demand.incomplete_cycles[0].known_active_count == 1
    assert result.zone_demand.incomplete_cycles[0].missing_zone_keys == ("down",)
    assert result.zone_demand.incomplete_cycles[0].short


def test_unknown_heat_demand_does_not_become_zero_and_no_hidden_few_zones_limit() -> None:
    zones = (Zone("up", "Boven"),)
    result = analyze_zone_context(
        zones,
        (cycle(START),),
        {"up": timeline(Role.ZONE_DEMAND, "up", True)},
        {},
        timeline(Role.HEAT_DEMAND, None, None),
        PERIOD,
        180_000,
    )

    assert result.zone_demand.availability == "not_available"
    assert result.zone_demand.unknown_demand_cycles == 1
    assert result.zone_demand.distribution == ()
    assert result.few_active_zones_max is None
