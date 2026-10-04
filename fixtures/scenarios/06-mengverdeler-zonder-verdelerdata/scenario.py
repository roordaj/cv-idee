"""Scenario 6: mixed installation (radiators + floor loop via mixing manifold) without manifold
measurements (requirements §9.6).

Mild cycling plus a living room that is comfortable and a bedroom that runs 3.5 K colder. There
are no manifold flow/return signals and no valve/zone signals, so a hydraulic conclusion is
limited and no loop-specific advice may be given.
"""

from cvidee.testing.generator import Behaviour, GeneratedData, GeneratorSpec, Period, generate

MIXED = Behaviour(
    burn_s=(420, 720),
    pause_s=(300, 480),
    block_s=(5400, 9000),
    idle_s=(1800, 3600),
    flow_setpoint_c=50.0,
    modulation_pct=28.0,
    bedroom_offset_c=-3.5,
)

SPEC = GeneratorSpec(
    seed=106,
    hours=72,
    periods=(Period(0, 72, MIXED),),
    dhw_per_day=3,
)


def build() -> GeneratedData:
    return generate(SPEC)
