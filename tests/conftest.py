"""Fixtures for SinricPro tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from custom_components.sinricpro.const import DOMAIN


@pytest.fixture
def mock_api() -> Generator[AsyncMock, None, None]:
    """Mock SinricPro API."""
    with patch("custom_components.sinricpro.api.SinricProApi", autospec=True) as mock:
        api = mock.return_value
        api.validate_api_key = AsyncMock(return_value=True)
        api.get_devices = AsyncMock(return_value=[])
        api.set_power_state = AsyncMock(return_value=True)
        yield api


@pytest.fixture
def mock_api_class() -> Generator[MagicMock, None, None]:
    """Mock SinricPro API class."""
    with patch("custom_components.sinricpro.api.SinricProApi", autospec=True) as mock_class:
        api = mock_class.return_value
        api.validate_api_key = AsyncMock(return_value=True)
        api.get_devices = AsyncMock(return_value=[])
        api.set_power_state = AsyncMock(return_value=True)
        yield mock_class


@pytest.fixture
def mock_sse() -> Generator[MagicMock, None, None]:
    """Mock SSE client."""
    with patch("custom_components.sinricpro.sse.SinricProSSE", autospec=True) as mock:
        sse = mock.return_value
        sse.connect = AsyncMock()
        sse.disconnect = AsyncMock()
        sse.connected = True
        yield sse


@pytest.fixture
def mock_sse_class() -> Generator[MagicMock, None, None]:
    """Mock SSE client class."""
    with patch("custom_components.sinricpro.sse.SinricProSSE", autospec=True) as mock_class:
        sse = mock_class.return_value
        sse.connect = AsyncMock()
        sse.disconnect = AsyncMock()
        sse.connected = True
        yield mock_class


@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Mock config entry."""
    entry = MagicMock()
    entry.domain = DOMAIN
    entry.data = {CONF_API_KEY: "test_api_key_12345"}
    entry.entry_id = "test_entry_id"
    entry.unique_id = "sinricpro_test"
    entry.title = "SinricPro"
    return entry


@pytest.fixture
def mock_devices() -> list[dict[str, Any]]:
    """Sample device data."""
    return [
        {
            "id": "device_123",
            "name": "Living Room Light",
            "deviceType": "switch",
            "powerState": "off",
        },
        {
            "id": "device_456",
            "name": "Kitchen Light",
            "deviceType": "switch",
            "powerState": "on",
        },
    ]


@pytest.fixture
def mock_non_switch_devices() -> list[dict[str, Any]]:
    """Sample non-switch device data."""
    return [
        {
            "id": "device_789",
            "name": "Thermostat",
            "deviceType": "thermostat",
            "temperature": 72,
        },
    ]


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock, None, None]:
    """Mock setting up a config entry."""
    with patch(
        "custom_components.sinricpro.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture
def mock_coordinator() -> Generator[MagicMock, None, None]:
    """Mock the coordinator."""
    with patch(
        "custom_components.sinricpro.coordinator.SinricProDataUpdateCoordinator",
        autospec=True,
    ) as mock_class:
        coordinator = mock_class.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_setup = AsyncMock()
        coordinator.async_shutdown = AsyncMock()
        coordinator.data = {}
        coordinator.last_update_success = True
        yield coordinator


@pytest.fixture
def hass(hass: HomeAssistant) -> HomeAssistant:
    """Return Home Assistant instance."""
    return hass
