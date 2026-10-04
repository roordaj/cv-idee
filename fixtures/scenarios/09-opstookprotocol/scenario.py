"""Scenario 9: heat-up protocol (screed drying) active (requirements §9.9).

Six days. Hours 48-96 are a special period ``opstookprotocol``: fixed 60 degrees C flow, very long
burns (2.5-3.5 h) with 15-25 minute pauses and permanent demand. The data stays visible, but the
period is excluded from normal optimisation and from the reference model. Before and after the
period the installation runs normally.
"""

from cvidee.testing.generator import Behaviour, GeneratedData, GeneratorSpec, Period, generate

NORMAL = Behaviour()
PROTOCOL = Behaviour(
    burn_s=(9000, 12600),
    pause_s=(900, 1500),
    block_s=(86400, 86400),
    idle_s=(600, 600),
    flow_setpoint_c=60.0,
    modulation_pct=55.0,
    room_c=22.0,
)

SPEC = GeneratorSpec(
    seed=109,
    hours=144,
    periods=(
        Period(0, 48, NORMAL),
        Period(48, 96, PROTOCOL, special="opstookprotocol"),
        Period(96, 144, NORMAL),
    ),
    dhw_per_day=2,
)


def build() -> GeneratedData:
    return generate(SPEC)
