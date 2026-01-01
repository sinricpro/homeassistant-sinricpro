"""Tests for SinricPro binary_sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import CONF_API_KEY

from custom_components.sinricpro.api import Device
from custom_components.sinricpro.binary_sensor import SinricProContactSensor
from custom_components.sinricpro.binary_sensor import SinricProMotionSensor
from custom_components.sinricpro.const import DEVICE_TYPE_CONTACT_SENSOR
from custom_components.sinricpro.const import DEVICE_TYPE_MOTION_SENSOR
from custom_components.sinricpro.const import DOMAIN
from custom_components.sinricpro.const import MANUFACTURER


@pytest.fixture
def mock_coordinator() -> MagicMock:
    """Create mock coordinator."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {}
    return coordinator


@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Create mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_API_KEY: "test_api_key"}
    return entry


@pytest.fixture
def mock_contact_device() -> Device:
    """Create mock contact sensor device."""
    return Device(
        id="contact_123",
        name="Test Contact Sensor",
        device_type=DEVICE_TYPE_CONTACT_SENSOR,
        raw_data={},
        contact_state="closed",
    )


@pytest.fixture
def mock_motion_device() -> Device:
    """Create mock motion sensor device."""
    return Device(
        id="motion_123",
        name="Test Motion Sensor",
        device_type=DEVICE_TYPE_MOTION_SENSOR,
        raw_data={},
        last_motion_state="notDetected",
    )


@pytest.fixture
def contact_sensor(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_contact_device: Device,
) -> SinricProContactSensor:
    """Create contact sensor entity."""
    mock_coordinator.data = {mock_contact_device.id: mock_contact_device}
    return SinricProContactSensor(mock_coordinator, mock_contact_device.id, mock_config_entry)


@pytest.fixture
def motion_sensor(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_motion_device: Device,
) -> SinricProMotionSensor:
    """Create motion sensor entity."""
    mock_coordinator.data = {mock_motion_device.id: mock_motion_device}
    return SinricProMotionSensor(mock_coordinator, mock_motion_device.id, mock_config_entry)


# Contact Sensor Tests
def test_contact_sensor_unique_id(
    contact_sensor: SinricProContactSensor,
    mock_config_entry: MagicMock,
    mock_contact_device: Device,
) -> None:
    """Test contact sensor unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_contact_device.id}"
    assert contact_sensor.unique_id == expected_id


def test_contact_sensor_name(contact_sensor: SinricProContactSensor) -> None:
    """Test contact sensor name."""
    assert contact_sensor.name is None


def test_contact_sensor_device_class(
    contact_sensor: SinricProContactSensor,
) -> None:
    """Test contact sensor device class."""
    assert contact_sensor.device_class == BinarySensorDeviceClass.DOOR


def test_contact_sensor_is_on_closed(
    contact_sensor: SinricProContactSensor,
) -> None:
    """Test contact sensor is_on when closed."""
    assert contact_sensor.is_on is False


def test_contact_sensor_is_on_open(
    contact_sensor: SinricProContactSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test contact sensor is_on when open."""
    open_device = Device(
        id="contact_123",
        name="Test Contact Sensor",
        device_type=DEVICE_TYPE_CONTACT_SENSOR,
        contact_state="open",
        raw_data={},
    )
    mock_coordinator.data = {open_device.id: open_device}
    assert contact_sensor.is_on is True


def test_contact_sensor_is_on_none_when_no_device(
    contact_sensor: SinricProContactSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test contact sensor is_on returns None when device not found."""
    mock_coordinator.data = {}
    assert contact_sensor.is_on is None


def test_contact_sensor_is_on_none_when_no_state(
    contact_sensor: SinricProContactSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test contact sensor is_on returns None when no contact state."""
    device_no_state = Device(
        id="contact_123",
        name="Test Contact Sensor",
        device_type=DEVICE_TYPE_CONTACT_SENSOR,
        contact_state=None,
        raw_data={},
    )
    mock_coordinator.data = {device_no_state.id: device_no_state}
    assert contact_sensor.is_on is None


def test_contact_sensor_available(
    contact_sensor: SinricProContactSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test contact sensor availability."""
    assert contact_sensor.available is True

    mock_coordinator.last_update_success = False
    assert contact_sensor.available is False


def test_contact_sensor_device_info(
    contact_sensor: SinricProContactSensor,
) -> None:
    """Test contact sensor device info."""
    device_info = contact_sensor.device_info

    assert device_info["identifiers"] == {(DOMAIN, "contact_123")}
    assert device_info["name"] == "Test Contact Sensor"
    assert device_info["manufacturer"] == MANUFACTURER
    assert device_info["model"] == "Contact Sensor"


# Motion Sensor Tests
def test_motion_sensor_unique_id(
    motion_sensor: SinricProMotionSensor,
    mock_config_entry: MagicMock,
    mock_motion_device: Device,
) -> None:
    """Test motion sensor unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_motion_device.id}"
    assert motion_sensor.unique_id == expected_id


def test_motion_sensor_name(motion_sensor: SinricProMotionSensor) -> None:
    """Test motion sensor name."""
    assert motion_sensor.name is None


def test_motion_sensor_device_class(
    motion_sensor: SinricProMotionSensor,
) -> None:
    """Test motion sensor device class."""
    assert motion_sensor.device_class == BinarySensorDeviceClass.MOTION


def test_motion_sensor_is_on_not_detected(
    motion_sensor: SinricProMotionSensor,
) -> None:
    """Test motion sensor is_on when not detected."""
    assert motion_sensor.is_on is False


def test_motion_sensor_is_on_detected(
    motion_sensor: SinricProMotionSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test motion sensor is_on when detected."""
    detected_device = Device(
        id="motion_123",
        name="Test Motion Sensor",
        device_type=DEVICE_TYPE_MOTION_SENSOR,
        last_motion_state="detected",
        raw_data={},
    )
    mock_coordinator.data = {detected_device.id: detected_device}
    assert motion_sensor.is_on is True


def test_motion_sensor_is_on_none_when_no_device(
    motion_sensor: SinricProMotionSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test motion sensor is_on returns None when device not found."""
    mock_coordinator.data = {}
    assert motion_sensor.is_on is None


def test_motion_sensor_is_on_none_when_no_state(
    motion_sensor: SinricProMotionSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test motion sensor is_on returns None when no motion state."""
    device_no_state = Device(
        id="motion_123",
        name="Test Motion Sensor",
        device_type=DEVICE_TYPE_MOTION_SENSOR,
        last_motion_state=None,
        raw_data={},
    )
    mock_coordinator.data = {device_no_state.id: device_no_state}
    assert motion_sensor.is_on is None


def test_motion_sensor_available(
    motion_sensor: SinricProMotionSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test motion sensor availability."""
    assert motion_sensor.available is True

    mock_coordinator.last_update_success = False
    assert motion_sensor.available is False


def test_motion_sensor_device_info(
    motion_sensor: SinricProMotionSensor,
) -> None:
    """Test motion sensor device info."""
    device_info = motion_sensor.device_info

    assert device_info["identifiers"] == {(DOMAIN, "motion_123")}
    assert device_info["name"] == "Test Motion Sensor"
    assert device_info["manufacturer"] == MANUFACTURER
    assert device_info["model"] == "Motion Sensor"
