"""Scenario 3: the burner stops after heat demand ended (requirements §9.3).

Short burns (2.5-4 min), but each one is a whole demand block: the thermostat ends the demand
and the burner stops with it. It looks like cycling but is not cycling during sustained demand.
"""

from cvidee.testing.generator import Behaviour, GeneratedData, GeneratorSpec, Period, generate

DEMAND_ENDS_WITH_BURN = Behaviour(
    burn_s=(300, 400),  # longer than any block, so the burn is cut off by the end of demand
    pause_s=(600, 900),
    block_s=(150, 240),
    idle_s=(900, 1800),
    flow_setpoint_c=40.0,
    modulation_pct=22.0,
)

SPEC = GeneratorSpec(
    seed=103,
    hours=48,
    periods=(Period(0, 48, DEMAND_ENDS_WITH_BURN),),
    dhw_per_day=2,
)


def build() -> GeneratedData:
    return generate(SPEC)
