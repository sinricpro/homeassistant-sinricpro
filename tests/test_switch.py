"""Tests for SinricPro switch platform."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinricpro.api import Device
from custom_components.sinricpro.const import DEVICE_TYPE_SWITCH
from custom_components.sinricpro.const import DOMAIN
from custom_components.sinricpro.const import MANUFACTURER
from custom_components.sinricpro.exceptions import (
    SinricProDeviceOfflineError,
    SinricProError,
    SinricProTimeoutError,
)
from custom_components.sinricpro.switch import SinricProSwitch


@pytest.fixture
def mock_coordinator() -> MagicMock:
    """Create mock coordinator."""
    coordinator = MagicMock()
    coordinator.api = MagicMock()
    coordinator.api.set_power_state = AsyncMock(return_value=True)
    coordinator.last_update_success = True
    coordinator.data = {}
    coordinator.update_device_state = MagicMock()
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Create mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_API_KEY: "test_api_key"}
    return entry


@pytest.fixture
def mock_device() -> Device:
    """Create mock device."""
    return Device(
        id="device_123",
        name="Test Switch",
        device_type=DEVICE_TYPE_SWITCH,
        power_state=False,
        raw_data={},
    )


@pytest.fixture
def switch(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_device: Device,
) -> SinricProSwitch:
    """Create switch entity."""
    mock_coordinator.data = {mock_device.id: mock_device}
    return SinricProSwitch(mock_coordinator, mock_device.id, mock_config_entry)


def test_switch_unique_id(
    switch: SinricProSwitch,
    mock_config_entry: MagicMock,
    mock_device: Device,
) -> None:
    """Test switch unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_device.id}"
    assert switch.unique_id == expected_id


def test_switch_name(switch: SinricProSwitch, mock_device: Device) -> None:
    """Test switch name."""
    assert switch.name == mock_device.name


def test_switch_is_on(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
    mock_device: Device,
) -> None:
    """Test switch is_on property."""
    assert switch.is_on is False

    # Change state
    mock_device_on = Device(
        id="device_123",
        name="Test Switch",
        device_type=DEVICE_TYPE_SWITCH,
        power_state=True,
        raw_data={},
    )
    mock_coordinator.data = {mock_device_on.id: mock_device_on}

    assert switch.is_on is True


def test_switch_available(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch availability."""
    assert switch.available is True

    mock_coordinator.last_update_success = False
    assert switch.available is False


def test_switch_available_no_device(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch availability when device not found."""
    mock_coordinator.data = {}
    assert switch.available is False


def test_switch_device_info(switch: SinricProSwitch) -> None:
    """Test switch device info."""
    device_info = switch.device_info

    assert device_info["identifiers"] == {(DOMAIN, "device_123")}
    assert device_info["name"] == "Test Switch"
    assert device_info["manufacturer"] == MANUFACTURER
    assert device_info["model"] == "Switch"


async def test_switch_turn_on(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning switch on."""
    await switch.async_turn_on()

    mock_coordinator.api.set_power_state.assert_called_once_with(
        "device_123", True
    )
    mock_coordinator.update_device_state.assert_called_with("device_123", True)


async def test_switch_turn_off(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning switch off."""
    await switch.async_turn_off()

    mock_coordinator.api.set_power_state.assert_called_once_with(
        "device_123", False
    )
    mock_coordinator.update_device_state.assert_called_with("device_123", False)


async def test_switch_turn_on_timeout_retry(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning switch on with timeout and retry."""
    # First call times out, second succeeds
    mock_coordinator.api.set_power_state = AsyncMock(
        side_effect=[SinricProTimeoutError("Timeout"), True]
    )

    await switch.async_turn_on()

    assert mock_coordinator.api.set_power_state.call_count == 2


async def test_switch_turn_on_timeout_retry_fails(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning switch on with timeout and retry failure."""
    mock_coordinator.api.set_power_state = AsyncMock(
        side_effect=SinricProTimeoutError("Timeout")
    )

    with pytest.raises(HomeAssistantError) as exc_info:
        await switch.async_turn_on()

    assert "timed out" in str(exc_info.value).lower()


async def test_switch_turn_on_device_offline(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning switch on when device is offline."""
    mock_coordinator.api.set_power_state = AsyncMock(
        side_effect=SinricProDeviceOfflineError("Device offline")
    )

    with pytest.raises(HomeAssistantError) as exc_info:
        await switch.async_turn_on()

    assert "offline" in str(exc_info.value).lower()


async def test_switch_turn_on_api_error(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning switch on with API error."""
    mock_coordinator.api.set_power_state = AsyncMock(
        side_effect=SinricProError("API error")
    )

    with pytest.raises(HomeAssistantError) as exc_info:
        await switch.async_turn_on()

    assert "API error" in str(exc_info.value)


async def test_switch_optimistic_update(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test optimistic state update."""
    # Track state changes
    states = []

    original_write = switch.async_write_ha_state

    def track_state() -> None:
        states.append(switch._optimistic_state)
        original_write()

    switch.async_write_ha_state = track_state

    await switch.async_turn_on()

    # Should have optimistic update (True) then clear (None)
    assert True in states
    assert switch._optimistic_state is None


async def test_switch_optimistic_update_revert_on_failure(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
    mock_device: Device,
) -> None:
    """Test optimistic state update reverts on failure."""
    # Set initial state
    mock_coordinator.data = {mock_device.id: mock_device}

    mock_coordinator.api.set_power_state = AsyncMock(
        side_effect=SinricProError("API error")
    )

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()

    # Optimistic state should be cleared
    assert switch._optimistic_state is None
    # Original state should be restored
    mock_coordinator.update_device_state.assert_called_with(
        "device_123", False  # Original state
    )


def test_switch_name_none_when_no_device(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch name returns None when device not found."""
    mock_coordinator.data = {}
    assert switch.name is None


def test_switch_is_on_none_when_no_device(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch is_on returns None when device not found."""
    mock_coordinator.data = {}
    assert switch.is_on is None


def test_switch_is_on_uses_optimistic_state(
    switch: SinricProSwitch,
) -> None:
    """Test switch is_on uses optimistic state when set."""
    switch._optimistic_state = True
    assert switch.is_on is True

    switch._optimistic_state = False
    assert switch.is_on is False


def test_switch_has_entity_name(switch: SinricProSwitch) -> None:
    """Test switch has_entity_name attribute."""
    assert switch._attr_has_entity_name is True
