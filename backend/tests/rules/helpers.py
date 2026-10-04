"""Builders shared by the rule tests."""

from __future__ import annotations

from cvidee.analysis.types import HOUR_MS, MINUTE_MS, BurnerCycle, EndReason, Mode, Role
from cvidee.rules.base import (
    CircuitFacts,
    CircuitKind,
    InstallationFacts,
    SignalStatus,
    signal_ref,
)

T0 = 1_791_064_800_000
"""Sunday 4 October 2026 00:00 Europe/Amsterdam (UTC+2)."""
DAY_MS = 24 * HOUR_MS

PROFILE = InstallationFacts(
    circuits=(
        CircuitFacts("beneden", CircuitKind.DIRECT, rooms=("woonkamer",)),
        CircuitFacts("boven", CircuitKind.MIXING_MANIFOLD, rooms=("slaapkamer",), manifold="boven"),
    ),
    rooms=("woonkamer", "slaapkamer"),
    version="p1",
)

BOILER_ROLES = (
    Role.FLAME,
    Role.OPERATING_MODE,
    Role.HEAT_DEMAND,
    Role.FLOW_SETPOINT,
    Role.FLOW_TEMPERATURE,
    Role.RETURN_TEMPERATURE,
    Role.MODULATION,
)


def status(
    role: Role,
    scope_key: str | None = None,
    *,
    coverage: float = 0.97,
    stale: bool = False,
    resolution_ms: int | None = 4_000,
) -> SignalStatus:
    return SignalStatus(signal_ref(role, scope_key), coverage, stale, resolution_ms)


def boiler_signals(*, without: tuple[Role, ...] = ()) -> tuple[SignalStatus, ...]:
    """The design v3 setup: CAN boiler signals mapped; no gas meter, no manifold data."""
    return tuple(status(role) for role in BOILER_ROLES if role not in without)


def cycle(start: int, minutes: float = 2.5, mode: Mode = Mode.CH) -> BurnerCycle:
    duration = int(minutes * MINUTE_MS)
    return BurnerCycle(
        start=start,
        end=start + duration,
        duration_ms=duration,
        complete=True,
        start_observed=True,
        mode=mode,
        end_reason=EndReason.DHW_ENDED if mode is Mode.DHW else EndReason.STOP_DURING_DEMAND,
        final=True,
    )
