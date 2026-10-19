"""Runtime configuration from environment variables.

Two deployment modes are detected automatically:

* **add-on** - running as a Home Assistant add-on. The Supervisor injects
  ``SUPERVISOR_TOKEN``; Home Assistant is reached through the Supervisor proxy and the
  MQTT broker details come from the Supervisor services API.
* **standalone** - any other container or local run. Home Assistant is reached via
  ``HA_URL`` + ``HA_TOKEN`` (long-lived access token) and MQTT via ``MQTT_*``.

The HA token is only used for reading and ``notify``; never to control devices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import aiohttp
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPERVISOR_WEBSOCKET_URL = "ws://supervisor/core/websocket"
SUPERVISOR_REST_URL = "http://supervisor/core/api"
SUPERVISOR_API_URL = "http://supervisor"


class DeploymentMode(StrEnum):
    """How the application is deployed."""

    ADDON = "addon"
    STANDALONE = "standalone"


class ConfigurationError(RuntimeError):
    """Raised when the configuration is incomplete for the requested operation."""


@dataclass(frozen=True, slots=True)
class HAConnection:
    """Where and how to reach Home Assistant."""

    websocket_url: str
    rest_url: str
    token: SecretStr


@dataclass(frozen=True, slots=True)
class MqttSettings:
    """Connection details for the MQTT broker used for the HA export."""

    host: str
    port: int
    username: str | None
    password: SecretStr | None


class Settings(BaseSettings):
    """Application settings, read from the environment (empty values count as unset)."""

    model_config = SettingsConfigDict(env_ignore_empty=True, extra="ignore", populate_by_name=True)

    supervisor_token: SecretStr | None = Field(default=None, alias="SUPERVISOR_TOKEN")
    ha_url: str | None = Field(default=None, alias="HA_URL")
    ha_token: SecretStr | None = Field(default=None, alias="HA_TOKEN")

    db_path: Path = Field(default=Path("./data/cvidee.sqlite"), alias="CVIDEE_DB_PATH")
    static_dir: Path | None = Field(default=None, alias="CVIDEE_STATIC_DIR")
    api_token: SecretStr | None = Field(default=None, alias="CVIDEE_API_TOKEN")
    log_level: str = Field(default="info", alias="CVIDEE_LOG_LEVEL")
    retention_days: int = Field(default=180, ge=1, alias="CVIDEE_RETENTION_DAYS")
    notify_target: str | None = Field(default=None, alias="CVIDEE_NOTIFY_TARGET")
    analysis_enabled: bool = Field(default=True, alias="CVIDEE_ANALYSIS_ENABLED")
    analysis_interval_s: float = Field(default=60.0, gt=0, alias="CVIDEE_ANALYSIS_INTERVAL_S")
    can_gateway_entity_id: str | None = Field(default=None, alias="CVIDEE_CAN_GATEWAY_ENTITY_ID")
    can_gateway_roles: str = Field(default="", alias="CVIDEE_CAN_GATEWAY_ROLES")
    stub_data: bool = Field(default=False, alias="CVIDEE_STUB_DATA")
    """Serve the design-v3 example data on all API routes (contract stubs, issue #11)."""

    export_url: str | None = Field(default=None, alias="CVIDEE_EXPORT_URL")

    mqtt_host: str | None = Field(default=None, alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT")
    mqtt_user: str | None = Field(default=None, alias="MQTT_USER")
    mqtt_password: SecretStr | None = Field(default=None, alias="MQTT_PASSWORD")

    @property
    def mode(self) -> DeploymentMode:
        """Add-on mode when the Supervisor provided a token, otherwise standalone."""
        if self.supervisor_token is not None:
            return DeploymentMode.ADDON
        return DeploymentMode.STANDALONE

    @property
    def api_auth_enabled(self) -> bool:
        """Bearer-token auth on ``/api`` applies to standalone mode only.

        In add-on mode Home Assistant ingress already authenticates the user.
        """
        return self.mode is DeploymentMode.STANDALONE and self.api_token is not None

    @property
    def ha_configured(self) -> bool:
        """Whether Home Assistant can be reached (add-on token, or ``HA_URL`` + ``HA_TOKEN``)."""
        return self.supervisor_token is not None or bool(self.ha_url and self.ha_token)

    def ha_connection(self) -> HAConnection:
        """Return how to reach Home Assistant for the detected mode."""
        if self.supervisor_token is not None:
            return HAConnection(
                websocket_url=SUPERVISOR_WEBSOCKET_URL,
                rest_url=SUPERVISOR_REST_URL,
                token=self.supervisor_token,
            )
        if not self.ha_url or self.ha_token is None:
            raise ConfigurationError("Standalone mode requires HA_URL and HA_TOKEN to be set.")
        base = self.ha_url.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base.removeprefix("https://")
        elif base.startswith("http://"):
            ws_base = "ws://" + base.removeprefix("http://")
        else:
            raise ConfigurationError("HA_URL must start with http:// or https://.")
        return HAConnection(
            websocket_url=f"{ws_base}/api/websocket",
            rest_url=f"{base}/api",
            token=self.ha_token,
        )

    def mqtt_settings_from_env(self) -> MqttSettings | None:
        """MQTT settings from ``MQTT_*`` (standalone mode); ``None`` if no host is set."""
        if not self.mqtt_host:
            return None
        return MqttSettings(
            host=self.mqtt_host,
            port=self.mqtt_port,
            username=self.mqtt_user,
            password=self.mqtt_password,
        )


async def fetch_mqtt_settings_from_supervisor(settings: Settings) -> MqttSettings | None:
    """Fetch the optional MQTT service; a missing service selects REST fallback."""
    if settings.supervisor_token is None:
        return None
    headers = {"Authorization": f"Bearer {settings.supervisor_token.get_secret_value()}"}
    async with (
        aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as http,
        http.get(f"{SUPERVISOR_API_URL}/services/mqtt") as response,
    ):
        if response.status in (400, 404):
            return None
        response.raise_for_status()
        payload = await response.json()
    if payload.get("result") != "ok":
        raise ConfigurationError("Supervisor MQTT service lookup failed")
    data = payload["data"]
    return MqttSettings(
        host=str(data["host"]),
        port=int(data["port"]),
        username=data.get("username"),
        password=SecretStr(data["password"]) if data.get("password") else None,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (read once from the environment)."""
    return Settings()
