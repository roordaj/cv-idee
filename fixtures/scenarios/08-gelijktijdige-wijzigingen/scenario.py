"""Scenario 8: two simultaneous changes and different weather (requirements §9.8, FR-32).

Six days; at hour 72 both the pump speed and the flow setpoint are changed in the same minute,
and the outdoor temperature drops 6 K at the same moment. Cycling improves afterwards, but the
effect can be attributed to neither parameter nor cleanly to the change: no finding may credit
one parameter, and the comparison is flagged as not comparable.
"""

from cvidee.testing.generator import (
    Behaviour,
    ChangeMarker,
    GeneratedData,
    GeneratorSpec,
    Period,
    WeatherShift,
    generate,
)

CHANGE_AT_H = 72.0

BEFORE = Behaviour(
    burn_s=(100, 170),
    pause_s=(240, 360),
    block_s=(7200, 14400),
    idle_s=(1800, 3600),
    flow_setpoint_c=55.0,
    modulation_pct=19.0,
)
AFTER = Behaviour(
    burn_s=(900, 1500),
    pause_s=(420, 600),
    block_s=(3600, 7200),
    idle_s=(1200, 2400),
    flow_setpoint_c=50.0,
    modulation_pct=34.0,
)

SPEC = GeneratorSpec(
    seed=108,
    hours=144,
    periods=(Period(0, CHANGE_AT_H, BEFORE), Period(CHANGE_AT_H, 144, AFTER)),
    dhw_per_day=2,
    outdoor_base_c=7.0,
    weather_shift=WeatherShift(CHANGE_AT_H, -6.0),
    changes=(
        ChangeMarker(CHANGE_AT_H, "pump_speed", "auto", "70%"),
        ChangeMarker(CHANGE_AT_H + 1 / 60, "flow_setpoint_max", "55", "50"),
    ),
)


def build() -> GeneratedData:
    return generate(SPEC)
