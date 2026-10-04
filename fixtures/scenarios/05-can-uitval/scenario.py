"""Scenario 5: CAN/Home Assistant data loss (requirements §9.5).

Short cycling before and after the outage, so a naive tool might read the silence as "problem
solved". Day 1: the CAN gateway is down 13:00-17:30 (gateway signals lost, room/outdoor
sensors keep reporting), with a reconnect poll afterwards. Day 2: our own HA WebSocket is down
09:00-10:30. Heartbeats are on so staleness and the derived gateway outage apply. The burner is
running at the moment the gateway comes back (the poll shows flame on): that must not become a
fictitious start.
"""

from cvidee.testing.generator import (
    Behaviour,
    DataGap,
    GeneratedData,
    GeneratorSpec,
    Period,
    generate,
)

SHORT_CYCLING = Behaviour(
    burn_s=(100, 160),
    pause_s=(200, 300),
    block_s=(10800, 18000),
    idle_s=(1200, 1800),
    flow_setpoint_c=55.0,
    modulation_pct=20.0,
)

SPEC = GeneratorSpec(
    seed=105,
    hours=36,
    periods=(Period(0, 36, SHORT_CYCLING),),
    dhw_per_day=2,
    heartbeat_s=60,
    data_gaps=(
        DataGap(13.0, 17.5, kind="can"),
        DataGap(33.0, 34.5, kind="ws"),
    ),
)


def build() -> GeneratedData:
    return generate(SPEC)
