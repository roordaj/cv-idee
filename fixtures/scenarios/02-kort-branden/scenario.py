"""Scenario 2: repeated short burns during sustained heat demand (requirements §9.2).

Three days; every demand block (2-4 h) holds 1.5-2.5 minute burns with 4-6 minute pauses while
demand continues, i.e. real short cycling. DHW draws are ordinary and must not count.
"""

from cvidee.testing.generator import Behaviour, GeneratedData, GeneratorSpec, Period, generate

SHORT_CYCLING = Behaviour(
    burn_s=(90, 150),
    pause_s=(240, 360),
    block_s=(7200, 14400),
    idle_s=(1800, 3600),
    flow_setpoint_c=55.0,
    modulation_pct=19.0,
)

SPEC = GeneratorSpec(
    seed=102,
    hours=72,
    periods=(Period(0, 72, SHORT_CYCLING),),
    dhw_per_day=2,
)


def build() -> GeneratedData:
    return generate(SPEC)
