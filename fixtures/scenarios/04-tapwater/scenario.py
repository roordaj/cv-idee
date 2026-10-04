"""Scenario 4: DHW cycles are excluded from CH temperature and cycling conclusions (§9.4).

Normal CH regime plus six DHW draws per day, many of them short (1-2.5 min) so they would look
like cycling if they were counted. DHW runs at flow 72 degrees C, far above the CH temperature.
"""

from cvidee.testing.generator import Behaviour, GeneratedData, GeneratorSpec, Period, generate

SPEC = GeneratorSpec(
    seed=104,
    hours=72,
    periods=(Period(0, 72, Behaviour()),),
    dhw_per_day=6,
    dhw_duration_s=(60, 150),
)


def build() -> GeneratedData:
    return generate(SPEC)
