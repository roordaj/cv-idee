"""Scenario 7: flow-temperature change with better cycles but worse comfort (requirements §9.7).

Six days, change at day 3 (hour 72): flow setpoint 55 -> 45 degrees C. Before: short cycling
(1.5-2.5 min burns). After: long, calm burns, but the living room settles 1.1 K colder. Weather
is the same before and after, so the periods are comparable. The change carries a rollback
criterion on comfort which is triggered.
"""

from cvidee.testing.generator import (
    Behaviour,
    ChangeMarker,
    GeneratedData,
    GeneratorSpec,
    Period,
    generate,
)

CHANGE_AT_H = 72.0

BEFORE = Behaviour(
    burn_s=(90, 150),
    pause_s=(240, 360),
    block_s=(7200, 14400),
    idle_s=(1800, 3600),
    flow_setpoint_c=55.0,
    modulation_pct=19.0,
    room_c=20.5,
)
AFTER = Behaviour(
    burn_s=(1200, 2100),
    pause_s=(480, 720),
    block_s=(3600, 7200),
    idle_s=(1800, 3600),
    flow_setpoint_c=45.0,
    modulation_pct=30.0,
    room_c=19.4,
)

SPEC = GeneratorSpec(
    seed=107,
    hours=144,
    periods=(Period(0, CHANGE_AT_H, BEFORE), Period(CHANGE_AT_H, 144, AFTER)),
    dhw_per_day=2,
    changes=(ChangeMarker(CHANGE_AT_H, "flow_setpoint_max", "55", "45"),),
)


def build() -> GeneratedData:
    return generate(SPEC)
