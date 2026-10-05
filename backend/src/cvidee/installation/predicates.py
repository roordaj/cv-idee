"""Predicates rules use on the installation profile (FR-02, FR-03).

All answer conservatively: an unknown room/circuit/spec is "no", never "yes".
"""

from __future__ import annotations

from cvidee.rules.base import CircuitFacts, CircuitKind, InstallationFacts


def _circuit_of_room(facts: InstallationFacts, room: str) -> CircuitFacts | None:
    for circuit in facts.circuits:
        if room in circuit.rooms:
            return circuit
    return None


def circuit_is_mixed(facts: InstallationFacts, room: str) -> bool:
    """Whether ``room`` is served via a mixing manifold (boiler ΔT is then not the loop ΔT)."""
    circuit = _circuit_of_room(facts, room)
    return circuit is not None and circuit.kind is CircuitKind.MIXING_MANIFOLD


def boiler_dt_representative(facts: InstallationFacts, circuit_key: str) -> bool:
    """Whether the boiler flow/return ΔT represents this circuit: only a direct circuit."""
    return any(c.key == circuit_key and c.kind is CircuitKind.DIRECT for c in facts.circuits)


def known(facts: InstallationFacts, spec: str) -> bool:
    """Whether the (boiler-level) specification has an explicitly known value."""
    return spec in facts.known_specs


def modulation_to_kw(facts: InstallationFacts, modulation_pct: float) -> float | None:
    """Power in kW for a modulation percentage, only with a validated conversion; else
    ``None`` (a modulation percentage is never shown as kW without one)."""
    if facts.modulation_kw_per_pct is None:
        return None
    return modulation_pct * facts.modulation_kw_per_pct
