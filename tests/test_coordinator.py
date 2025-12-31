"""Tests for SinricPro data coordinator."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sinricpro.api import Device
from custom_components.sinricpro.coordinator import SinricProDataUpdateCoordinator
from custom_components.sinricpro.exceptions import (
    SinricProAuthenticationError,
    SinricProConnectionError,
    SinricProRateLimitError,
    SinricProTimeoutError,
)


@pytest.fixture
def mock_api() -> AsyncMock:
    """Create mock API."""
    api = AsyncMock()
    api.get_devices = AsyncMock(return_value=[])
    return api


@pytest.fixture
def mock_session() -> MagicMock:
    """Create mock session."""
    return MagicMock()


@pytest.fixture
def coordinator(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_session: MagicMock,
) -> SinricProDataUpdateCoordinator:
    """Create coordinator."""
    return SinricProDataUpdateCoordinator(
        hass,
        mock_api,
        mock_session,
        "test_api_key",
    )


async def test_coordinator_initial_fetch(
    coordinator: SinricProDataUpdateCoordinator,
    mock_api: AsyncMock,
) -> None:
    """Test initial data fetch."""
    devices = [
        Device(
            id="device_123",
            name="Test Device",
            device_type="switch",
            power_state=True,
            raw_data={},
        )
    ]
    mock_api.get_devices.return_value = devices

    data = await coordinator._async_update_data()

    assert len(data) == 1
    assert "device_123" in data
    assert data["device_123"].name == "Test Device"


async def test_coordinator_refresh(
    coordinator: SinricProDataUpdateCoordinator,
    mock_api: AsyncMock,
) -> None:
    """Test data refresh."""
    # Initial fetch
    devices1 = [
        Device(
            id="device_123",
            name="Test Device",
            device_type="switch",
            power_state=False,
            raw_data={},
        )
    ]
    mock_api.get_devices.return_value = devices1
    await coordinator._async_update_data()

    # Updated data
    devices2 = [
        Device(
            id="device_123",
            name="Test Device",
            device_type="switch",
            power_state=True,
            raw_data={},
        )
    ]
    mock_api.get_devices.return_value = devices2

    data = await coordinator._async_update_data()

    assert data["device_123"].power_state is True


async def test_coordinator_auth_error_triggers_reauth(
    coordinator: SinricProDataUpdateCoordinator,
    mock_api: AsyncMock,
) -> None:
    """Test authentication error triggers reauthentication."""
    mock_api.get_devices.side_effect = SinricProAuthenticationError(
        "Invalid API key"
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_connection_error(
    coordinator: SinricProDataUpdateCoordinator,
    mock_api: AsyncMock,
) -> None:
    """Test connection error handling."""
    mock_api.get_devices.side_effect = SinricProConnectionError(
        "Connection failed"
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_timeout_error(
    coordinator: SinricProDataUpdateCoordinator,
    mock_api: AsyncMock,
) -> None:
    """Test timeout error handling."""
    mock_api.get_devices.side_effect = SinricProTimeoutError(
        "Request timed out"
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_rate_limit_error(
    coordinator: SinricProDataUpdateCoordinator,
    mock_api: AsyncMock,
) -> None:
    """Test rate limit error handling."""
    mock_api.get_devices.side_effect = SinricProRateLimitError(
        "Rate limit exceeded",
        retry_after=1,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_unknown_error(
    coordinator: SinricProDataUpdateCoordinator,
    mock_api: AsyncMock,
) -> None:
    """Test unknown error handling."""
    mock_api.get_devices.side_effect = Exception("Unknown error")

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


def test_coordinator_handle_sse_event(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test handling SSE events."""
    # Setup initial device
    coordinator._devices = {
        "device_123": Device(
            id="device_123",
            name="Test Device",
            device_type="switch",
            power_state=False,
            raw_data={},
        )
    }

    # Simulate SSE event
    coordinator._handle_sse_event(
        "device_123",
        {"powerState": "on"},
    )

    assert coordinator._devices["device_123"].power_state is True


def test_coordinator_handle_sse_event_with_value(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test handling SSE events with value structure."""
    coordinator._devices = {
        "device_456": Device(
            id="device_456",
            name="Test Device",
            device_type="switch",
            power_state=True,
            raw_data={},
        )
    }

    coordinator._handle_sse_event(
        "device_456",
        {"value": {"state": "off"}},
    )

    assert coordinator._devices["device_456"].power_state is False


def test_coordinator_handle_sse_event_unknown_device(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test handling SSE event for unknown device."""
    coordinator._devices = {}

    # Should not raise
    coordinator._handle_sse_event(
        "unknown_device",
        {"powerState": "on"},
    )


def test_coordinator_handle_sse_event_no_state_change(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test handling SSE event with no state change."""
    coordinator._devices = {
        "device_123": Device(
            id="device_123",
            name="Test Device",
            device_type="switch",
            power_state=True,
            raw_data={},
        )
    }

    # Same state, should not trigger update notification
    coordinator._handle_sse_event(
        "device_123",
        {"powerState": "on"},
    )

    # State should remain the same
    assert coordinator._devices["device_123"].power_state is True


def test_coordinator_update_device_state(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test updating device state locally."""
    coordinator._devices = {
        "device_123": Device(
            id="device_123",
            name="Test Device",
            device_type="switch",
            power_state=False,
            raw_data={},
        )
    }

    coordinator.update_device_state("device_123", True)

    assert coordinator._devices["device_123"].power_state is True


def test_coordinator_update_device_state_unknown_device(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test updating state for unknown device."""
    coordinator._devices = {}

    # Should not raise
    coordinator.update_device_state("unknown_device", True)


def test_coordinator_get_device(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test getting device by ID."""
    device = Device(
        id="device_123",
        name="Test Device",
        device_type="switch",
        power_state=True,
        raw_data={},
    )
    coordinator._devices = {"device_123": device}

    result = coordinator.get_device("device_123")

    assert result is device


def test_coordinator_get_device_not_found(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test getting unknown device."""
    coordinator._devices = {}

    result = coordinator.get_device("unknown_device")

    assert result is None


async def test_coordinator_setup(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test coordinator setup."""
    with patch(
        "custom_components.sinricpro.coordinator.SinricProSSE"
    ) as mock_sse_class:
        mock_sse = mock_sse_class.return_value
        mock_sse.connect = AsyncMock()

        await coordinator.async_setup()

        mock_sse.connect.assert_called_once()


async def test_coordinator_shutdown(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test coordinator shutdown."""
    mock_sse = MagicMock()
    mock_sse.disconnect = AsyncMock()
    coordinator._sse = mock_sse

    await coordinator.async_shutdown()

    mock_sse.disconnect.assert_called_once()
    assert coordinator._sse is None


def test_coordinator_sse_connected(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test SSE connected property."""
    assert not coordinator.sse_connected

    mock_sse = MagicMock()
    mock_sse.connected = True
    coordinator._sse = mock_sse

    assert coordinator.sse_connected


def test_coordinator_sse_not_connected(
    coordinator: SinricProDataUpdateCoordinator,
) -> None:
    """Test SSE not connected property."""
    mock_sse = MagicMock()
    mock_sse.connected = False
    coordinator._sse = mock_sse

    assert not coordinator.sse_connected
