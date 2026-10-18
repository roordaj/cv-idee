"""Owned MQTT entities and discovery payloads; no command topics exist."""

from dataclasses import dataclass, field
from typing import Any

from cvidee import __version__

STATUS_TOPIC = "cv_analyse/status"
BIRTH_TOPIC = "homeassistant/status"


@dataclass(frozen=True)
class ExportEntity:
    key: str
    name: str
    component: str = "sensor"
    unit: str | None = None
    options: tuple[str, ...] = ()
    problem: bool = False

    @property
    def entity_id(self) -> str:
        return f"{self.component}.cv_analyse_{self.key}"

    @property
    def config_topic(self) -> str:
        return f"homeassistant/{self.component}/cv_analyse/{self.key}/config"

    @property
    def state_topic(self) -> str:
        return f"cv_analyse/{self.key}/state"

    @property
    def attributes_topic(self) -> str:
        return f"cv_analyse/{self.key}/attributes"

    def discovery(self, configuration_url: str | None = None) -> dict[str, Any]:
        device: dict[str, Any] = {
            "identifiers": ["cv_analyse"],
            "name": "CV-analyse",
            "manufacturer": "CV-idee",
            "model": "CV-analyse",
            "sw_version": __version__,
        }
        if configuration_url:
            device["configuration_url"] = configuration_url
        result: dict[str, Any] = {
            "name": self.name,
            "unique_id": f"cv_analyse_{self.key}",
            "default_entity_id": self.entity_id,
            "state_topic": self.state_topic,
            "json_attributes_topic": self.attributes_topic,
            "availability_topic": STATUS_TOPIC,
            "device": device,
        }
        if self.unit is not None or self.key in ("korte_cycli_6u", "open_bevindingen"):
            result["state_class"] = "measurement"
        if self.unit:
            result["unit_of_measurement"] = self.unit
        if self.options:
            result.update(device_class="enum", options=list(self.options))
        if self.problem:
            result.update(device_class="problem", payload_on="on", payload_off="off")
        return result


ENTITIES = (
    ExportEntity("starts_per_uur", "Starts per uur", unit="1/h"),
    ExportEntity("korte_cycli_6u", "Korte cycli 6u"),
    ExportEntity("gegevensdekking", "Gegevensdekking", unit="%"),
    ExportEntity("open_bevindingen", "Open bevindingen"),
    ExportEntity(
        "hoogste_ernst", "Hoogste ernst", options=("hoog", "middel", "laag", "info", "geen")
    ),
    ExportEntity("volgende_actie", "Volgende actie"),
    ExportEntity(
        "bedrijfsmodus",
        "Bedrijfsmodus",
        options=("cv", "tapwater", "standby", "naloop", "storing", "onbekend"),
    ),
    ExportEntity("onvoldoende_gegevens", "Onvoldoende gegevens", "binary_sensor", problem=True),
)
BY_KEY = {entity.key: entity for entity in ENTITIES}


@dataclass(frozen=True)
class ExportValue:
    state: str
    attributes: dict[str, Any] = field(default_factory=dict)


def validate_publish_topic(topic: str) -> None:
    """Enforce ownership even for retained cleanup; wildcards are never publish topics."""
    parts = topic.split("/")
    owned = (len(parts) >= 2 and parts[0] == "cv_analyse") or (
        len(parts) == 5
        and parts[0] == "homeassistant"
        and parts[1] in ("sensor", "binary_sensor")
        and parts[2] == "cv_analyse"
        and parts[4] == "config"
    )
    if not owned or any(not part or "+" in part or "#" in part for part in parts):
        raise ValueError("MQTT publication must stay within CV-analyse topics")
