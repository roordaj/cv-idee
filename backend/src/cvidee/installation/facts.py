"""Map a stored profile version to the read-only view rules consume."""

from __future__ import annotations

from cvidee.installation.specs import (
    MAX_FLOW,
    MAX_POWER,
    MIN_POWER,
    MODULATION_TO_KW,
    PUMP_SETTING,
)
from cvidee.rules.base import BoilerFacts, CircuitFacts, InstallationFacts
from cvidee.store.enums import CircuitKind, SpecStatus
from cvidee.store.models import InstallationProfile, InstallationSpec


def _num(spec: InstallationSpec | None) -> float | None:
    if spec is None or spec.status is not SpecStatus.KNOWN:
        return None
    return spec.value_num


def profile_facts(profile: InstallationProfile | None) -> InstallationFacts:
    """Facts of ``profile``; unknown (or not applicable) specs stay ``None``, never a guess."""
    if profile is None:
        return InstallationFacts()
    specs = {s.key: s for s in profile.specs if s.scope_key == ""}
    pump = specs.get(PUMP_SETTING)
    boiler = BoilerFacts(
        model=profile.details.get("boiler", {}).get("model"),
        max_flow_c=_num(specs.get(MAX_FLOW)),
        max_ch_power_kw=_num(specs.get(MAX_POWER)),
        min_power_kw=_num(specs.get(MIN_POWER)),
        pump_setting=(
            pump.value_text
            if pump.value_text is not None
            else (f"{pump.value_num:g}" if pump.value_num is not None else None)
        )
        if pump is not None and pump.status is SpecStatus.KNOWN
        else None,
    )
    circuits = tuple(
        CircuitFacts(
            key=c.key,
            kind=c.kind,
            rooms=tuple(sorted(r.key for r in profile.rooms if r.circuit_key == c.key)),
            manifold=c.key if c.kind is CircuitKind.MIXING_MANIFOLD else None,
        )
        for c in sorted(profile.circuits, key=lambda c: c.key)
    )
    return InstallationFacts(
        boiler=boiler,
        circuits=circuits,
        rooms=tuple(sorted(r.key for r in profile.rooms)),
        zones=tuple(sorted(z.key for z in profile.zones)),
        loops=tuple(
            sorted(
                loop["key"]
                for circuit in profile.details.get("circuits", {}).values()
                for loop in circuit.get("loops_inventory", [])
            )
        ),
        version=str(profile.id) if profile.id is not None else "default",
        known_specs=frozenset(k for k, s in specs.items() if s.status is SpecStatus.KNOWN),
        modulation_kw_per_pct=_kw_per_pct(specs.get(MODULATION_TO_KW)),
    )


def _kw_per_pct(spec: InstallationSpec | None) -> float | None:
    """kW per modulation percent; only from a known spec (a validated conversion)."""
    value = _num(spec)
    return None if value is None or value <= 0 else value
