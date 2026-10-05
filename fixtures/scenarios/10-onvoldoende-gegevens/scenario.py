"""Scenario 10: insufficient data (requirements §9.10).

Only six hours of data and only flame, flow temperature and outdoor temperature: no heat demand,
operating mode, return, modulation or room temperature. Cycles can be counted but not
classified; the outcome is "insufficient evidence" with the missing measurements named.
"""

from cvidee.testing.generator import (
    FLAME,
    FLOW,
    OUTDOOR,
    Behaviour,
    GeneratedData,
    GeneratorSpec,
    Period,
    generate,
)

SPEC = GeneratorSpec(
    seed=110,
    hours=6,
    periods=(Period(0, 6, Behaviour(burn_s=(150, 300), pause_s=(300, 600), block_s=(3600, 7200))),),
    include=frozenset({FLAME, FLOW, OUTDOOR}),
)


def build() -> GeneratedData:
    return generate(SPEC)
