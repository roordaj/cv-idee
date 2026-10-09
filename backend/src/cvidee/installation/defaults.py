"""Default profile for the starting situation (FR-02): radiators downstairs on the boiler
circuit, underfloor heating upstairs behind a mixing manifold with 5 groups. Every
specification starts as explicitly ``unknown``."""

from __future__ import annotations

from cvidee.installation.specs import SPEC_CATALOGUE
from cvidee.store.enums import CircuitKind, EmitterType, SpecStatus
from cvidee.store.models import (
    InstallationProfile,
    InstallationSpec,
    ProfileCircuit,
    ProfileRoom,
)

DOWNSTAIRS = ("woonkamer", "keuken", "hal")
UPSTAIRS = ("slaapkamer", "kinderkamer", "badkamer")
_NAMES = {
    "woonkamer": "Woonkamer",
    "keuken": "Keuken",
    "hal": "Hal",
    "slaapkamer": "Slaapkamer",
    "kinderkamer": "Kinderkamer",
    "badkamer": "Badkamer",
}


def default_profile(now_ts: int) -> InstallationProfile:
    """A new, unsaved default profile version valid from the beginning of time."""
    rooms = [
        ProfileRoom(
            key=key,
            name=_NAMES[key],
            circuit_key="beneden" if key in DOWNSTAIRS else "boven",
            has_thermostat=key == "woonkamer",
            is_demand_source=key == "woonkamer",
        )
        for key in (*DOWNSTAIRS, *UPSTAIRS)
    ]
    return InstallationProfile(
        valid_from_ts=0,
        created_at_ts=now_ts,
        note="Standaardprofiel",
        details={
            "boiler": {
                "model": "Remeha Calenta Ace",
                "control": "eTwist, modulerend",
                "data_source": "CAN-bus → Home Assistant",
                "heat_demand_source": "eTwist in de woonkamer",
            },
            "circuits": {
                "beneden": {
                    "loops": None,
                    "note": "Radiatoren hangen direct aan de ketel, dus ketelaanvoer en "
                    "-retour zijn hier representatief.",
                },
                "boven": {
                    "loops": 5,
                    "note": "De mengverdeler mengt heet ketelwater met retourwater tot een "
                    "lagere vloertemperatuur. Ketelmetingen zeggen daarom weinig over de "
                    "vloer; zonder verdelersensoren geen advies per groep.",
                },
            },
            "rooms": {
                key: {
                    "has_sensor": key in ("woonkamer", "slaapkamer"),
                    "schedule_text": None,
                    "setpoint": None,
                    "night_setpoint": None,
                }
                for key in _NAMES
            },
        },
        circuits=[
            ProfileCircuit(
                key="beneden",
                name="Beneden",
                kind=CircuitKind.DIRECT,
                emitter=EmitterType.RADIATOR,
            ),
            ProfileCircuit(
                key="boven",
                name="Boven",
                kind=CircuitKind.MIXING_MANIFOLD,
                emitter=EmitterType.UNDERFLOOR,
            ),
        ],
        rooms=rooms,
        specs=[
            InstallationSpec(
                scope_key="",
                key=s.key,
                status=SpecStatus.UNKNOWN,
                unit=s.unit,
                note="nog niet ingevuld",
            )
            for s in SPEC_CATALOGUE
        ],
    )
