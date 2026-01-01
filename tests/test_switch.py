"""Tests for SinricPro switch platform."""
from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_API_KEY

from custom_components.sinricpro.api import Device
from custom_components.sinricpro.const import DEVICE_TYPE_SWITCH
from custom_components.sinricpro.const import DOMAIN
from custom_components.sinricpro.const import MANUFACTURER
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
        raw_data={},
        power_state=False,
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


def test_switch_is_on_false(
    switch: SinricProSwitch,
) -> None:
    """Test switch is_on property when off."""
    assert switch.is_on is False


def test_switch_is_on_true(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch is_on property when on."""
    # Change state to on
    mock_device_on = Device(
        id="device_123",
        name="Test Switch",
        device_type=DEVICE_TYPE_SWITCH,
        raw_data={},
        power_state=True,
    )
    mock_coordinator.data = {mock_device_on.id: mock_device_on}

    assert switch.is_on is True


def test_switch_is_on_none_when_no_device(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch is_on returns None when device not found."""
    mock_coordinator.data = {}
    assert switch.is_on is None


def test_switch_available_true(
    switch: SinricProSwitch,
) -> None:
    """Test switch availability when coordinator is successful."""
    assert switch.available is True


def test_switch_available_false_coordinator_failed(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch availability when coordinator fails."""
    mock_coordinator.last_update_success = False
    assert switch.available is False


def test_switch_available_false_no_device(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch availability when device not found."""
    mock_coordinator.data = {}
    assert switch.available is False


def test_switch_device_info(
    switch: SinricProSwitch,
    mock_device: Device,
) -> None:
    """Test switch device info."""
    device_info = switch.device_info

    assert device_info["identifiers"] == {(DOMAIN, mock_device.id)}
    assert device_info["name"] == mock_device.name
    assert device_info["manufacturer"] == MANUFACTURER
    assert device_info["model"] == "Switch"


def test_switch_name_none_when_no_device(
    switch: SinricProSwitch,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch name returns None when device not found."""
    mock_coordinator.data = {}
    assert switch.name is None


def test_switch_has_entity_name(switch: SinricProSwitch) -> None:
    """Test switch has_entity_name attribute."""
    assert switch._attr_has_entity_name is True


def test_switch_device_class_is_none(switch: SinricProSwitch) -> None:
    """Test switch device class is None (generic switch)."""
    assert switch.device_class is None


def test_switch_should_poll_false(switch: SinricProSwitch) -> None:
    """Test switch should not poll (uses coordinator)."""
    assert switch.should_poll is False
