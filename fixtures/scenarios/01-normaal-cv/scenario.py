"""Scenario 1: long-running central heating without relevant deviation (requirements §9.1).

Three days, healthy cycles (15-30 min burns, 8-12 min pauses inside demand blocks), a few DHW
draws per day, all signals present, no gaps. Measurements are shown; no finding is expected.
"""

from cvidee.testing.generator import Behaviour, GeneratedData, GeneratorSpec, Period, generate

SPEC = GeneratorSpec(
    seed=101,
    hours=72,
    periods=(Period(0, 72, Behaviour()),),
    dhw_per_day=3,
)


def build() -> GeneratedData:
    return generate(SPEC)
