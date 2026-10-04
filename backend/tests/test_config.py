"""Tests for configuration, deployment-mode detection and optional API token auth."""

from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr

from cvidee.config import (
    SUPERVISOR_REST_URL,
    SUPERVISOR_WEBSOCKET_URL,
    ConfigurationError,
    DeploymentMode,
    Settings,
    fetch_mqtt_settings_from_supervisor,
)
from cvidee.main import create_app

_ENV_VARS = (
    "SUPERVISOR_TOKEN",
    "HA_URL",
    "HA_TOKEN",
    "CVIDEE_API_TOKEN",
    "CVIDEE_STATIC_DIR",
    "MQTT_HOST",
    "MQTT_PORT",
    "MQTT_USER",
    "MQTT_PASSWORD",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_addon_mode_uses_supervisor_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup-token")
    monkeypatch.setenv("HA_URL", "http://ignored:8123")
    settings = Settings()
    assert settings.mode is DeploymentMode.ADDON
    conn = settings.ha_connection()
    assert conn.websocket_url == SUPERVISOR_WEBSOCKET_URL
    assert conn.rest_url == SUPERVISOR_REST_URL
    assert conn.token.get_secret_value() == "sup-token"


@pytest.mark.parametrize(
    ("ha_url", "ws_url", "rest_url"),
    [
        ("http://ha.local:8123/", "ws://ha.local:8123/api/websocket", "http://ha.local:8123/api"),
        ("https://ha.example", "wss://ha.example/api/websocket", "https://ha.example/api"),
    ],
)
def test_standalone_mode_derives_urls(
    monkeypatch: pytest.MonkeyPatch, ha_url: str, ws_url: str, rest_url: str
) -> None:
    monkeypatch.setenv("HA_URL", ha_url)
    monkeypatch.setenv("HA_TOKEN", "llat")
    settings = Settings()
    assert settings.mode is DeploymentMode.STANDALONE
    conn = settings.ha_connection()
    assert (conn.websocket_url, conn.rest_url) == (ws_url, rest_url)


def test_standalone_without_token_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HA_URL", "http://ha.local:8123")
    monkeypatch.setenv("HA_TOKEN", "")  # empty counts as unset
    with pytest.raises(ConfigurationError):
        Settings().ha_connection()


def test_mqtt_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings().mqtt_settings_from_env() is None
    monkeypatch.setenv("MQTT_HOST", "mosquitto")
    monkeypatch.setenv("MQTT_PORT", "1884")
    monkeypatch.setenv("MQTT_USER", "dev")
    mqtt = Settings().mqtt_settings_from_env()
    assert mqtt is not None
    assert (mqtt.host, mqtt.port, mqtt.username) == ("mosquitto", 1884, "dev")


async def test_supervisor_mqtt_stub_returns_none() -> None:
    assert await fetch_mqtt_settings_from_supervisor(Settings()) is None


def _client(settings: Settings) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app(settings))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def protected_client() -> AsyncIterator[httpx.AsyncClient]:
    async with _client(Settings(CVIDEE_API_TOKEN=SecretStr("s3cret"))) as ac:
        yield ac


async def test_api_token_required_when_configured(protected_client: httpx.AsyncClient) -> None:
    assert (await protected_client.get("/api/unknown")).status_code == 401
    wrong = await protected_client.get("/api/unknown", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    ok = await protected_client.get("/api/unknown", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 404  # authenticated, route simply does not exist


async def test_health_is_public_with_api_token(protected_client: httpx.AsyncClient) -> None:
    assert (await protected_client.get("/api/health")).status_code == 200


async def test_api_token_ignored_in_addon_mode() -> None:
    settings = Settings(SUPERVISOR_TOKEN=SecretStr("sup"), CVIDEE_API_TOKEN=SecretStr("s3cret"))
    assert not settings.api_auth_enabled
    async with _client(settings) as ac:
        assert (await ac.get("/api/unknown")).status_code == 404
