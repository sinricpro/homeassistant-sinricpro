"""Tests for SinricPro sensor platform."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
from homeassistant.const import CONF_API_KEY
from homeassistant.const import PERCENTAGE
from homeassistant.const import UnitOfTemperature

from custom_components.sinricpro.api import Device
from custom_components.sinricpro.const import DEVICE_TYPE_AIR_QUALITY_SENSOR
from custom_components.sinricpro.const import DEVICE_TYPE_DOORBELL
from custom_components.sinricpro.const import DEVICE_TYPE_TEMPERATURE_SENSOR
from custom_components.sinricpro.const import DOMAIN
from custom_components.sinricpro.const import MANUFACTURER
from custom_components.sinricpro.sensor import SinricProAirQualityPM1Sensor
from custom_components.sinricpro.sensor import SinricProAirQualityPM10Sensor
from custom_components.sinricpro.sensor import SinricProAirQualityPM25Sensor
from custom_components.sinricpro.sensor import SinricProDoorbellLastRingSensor
from custom_components.sinricpro.sensor import SinricProHumiditySensor
from custom_components.sinricpro.sensor import SinricProTemperatureSensor


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
def mock_doorbell_device() -> Device:
    """Create mock doorbell device."""
    return Device(
        id="doorbell_123",
        name="Test Doorbell",
        device_type=DEVICE_TYPE_DOORBELL,
        raw_data={},
        last_doorbell_ring="2024-01-01T12:30:45Z",
    )


@pytest.fixture
def mock_air_quality_device() -> Device:
    """Create mock air quality sensor device."""
    return Device(
        id="airquality_123",
        name="Test Air Quality Sensor",
        device_type=DEVICE_TYPE_AIR_QUALITY_SENSOR,
        pm1=10.5,
        pm2_5=25.3,
        pm10=50.8,
        raw_data={},
    )


@pytest.fixture
def mock_temperature_device() -> Device:
    """Create mock temperature sensor device."""
    return Device(
        id="temp_123",
        name="Test Temperature Sensor",
        device_type=DEVICE_TYPE_TEMPERATURE_SENSOR,
        raw_data={},
        temperature=22.5,
        humidity=65.0,
    )


# Doorbell Last Ring Sensor Tests
@pytest.fixture
def doorbell_sensor(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_doorbell_device: Device,
) -> SinricProDoorbellLastRingSensor:
    """Create doorbell last ring sensor entity."""
    mock_coordinator.data = {mock_doorbell_device.id: mock_doorbell_device}
    return SinricProDoorbellLastRingSensor(
        mock_coordinator, mock_doorbell_device.id, mock_config_entry
    )


def test_doorbell_sensor_unique_id(
    doorbell_sensor: SinricProDoorbellLastRingSensor,
    mock_config_entry: MagicMock,
    mock_doorbell_device: Device,
) -> None:
    """Test doorbell sensor unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_doorbell_device.id}_last_ring"
    assert doorbell_sensor.unique_id == expected_id


def test_doorbell_sensor_name(
    doorbell_sensor: SinricProDoorbellLastRingSensor,
) -> None:
    """Test doorbell sensor name."""
    assert doorbell_sensor.name == "Last Ring"


def test_doorbell_sensor_device_class(
    doorbell_sensor: SinricProDoorbellLastRingSensor,
) -> None:
    """Test doorbell sensor device class."""
    assert doorbell_sensor.device_class == SensorDeviceClass.TIMESTAMP


def test_doorbell_sensor_native_value(
    doorbell_sensor: SinricProDoorbellLastRingSensor,
) -> None:
    """Test doorbell sensor native value."""
    # native_value returns a datetime object, not a string
    assert doorbell_sensor.native_value is not None


def test_doorbell_sensor_native_value_none_when_no_device(
    doorbell_sensor: SinricProDoorbellLastRingSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test doorbell sensor native value returns None when device not found."""
    mock_coordinator.data = {}
    assert doorbell_sensor.native_value is None


def test_doorbell_sensor_available(
    doorbell_sensor: SinricProDoorbellLastRingSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test doorbell sensor availability."""
    assert doorbell_sensor.available is True

    mock_coordinator.last_update_success = False
    assert doorbell_sensor.available is False


def test_doorbell_sensor_device_info(
    doorbell_sensor: SinricProDoorbellLastRingSensor,
) -> None:
    """Test doorbell sensor device info."""
    device_info = doorbell_sensor.device_info

    assert device_info["identifiers"] == {(DOMAIN, "doorbell_123")}
    assert device_info["name"] == "Test Doorbell"
    assert device_info["manufacturer"] == MANUFACTURER
    assert device_info["model"] == "Doorbell"


# Air Quality PM1 Sensor Tests
@pytest.fixture
def pm1_sensor(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_air_quality_device: Device,
) -> SinricProAirQualityPM1Sensor:
    """Create PM1 sensor entity."""
    mock_coordinator.data = {mock_air_quality_device.id: mock_air_quality_device}
    return SinricProAirQualityPM1Sensor(
        mock_coordinator, mock_air_quality_device.id, mock_config_entry
    )


def test_pm1_sensor_unique_id(
    pm1_sensor: SinricProAirQualityPM1Sensor,
    mock_config_entry: MagicMock,
    mock_air_quality_device: Device,
) -> None:
    """Test PM1 sensor unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_air_quality_device.id}_pm1"
    assert pm1_sensor.unique_id == expected_id


def test_pm1_sensor_name(pm1_sensor: SinricProAirQualityPM1Sensor) -> None:
    """Test PM1 sensor name."""
    assert pm1_sensor.name == "PM1.0"


def test_pm1_sensor_device_class(
    pm1_sensor: SinricProAirQualityPM1Sensor,
) -> None:
    """Test PM1 sensor device class."""
    assert pm1_sensor.device_class == SensorDeviceClass.PM1


def test_pm1_sensor_state_class(
    pm1_sensor: SinricProAirQualityPM1Sensor,
) -> None:
    """Test PM1 sensor state class."""
    assert pm1_sensor.state_class == SensorStateClass.MEASUREMENT


def test_pm1_sensor_unit(pm1_sensor: SinricProAirQualityPM1Sensor) -> None:
    """Test PM1 sensor unit."""
    assert pm1_sensor.native_unit_of_measurement == CONCENTRATION_MICROGRAMS_PER_CUBIC_METER


def test_pm1_sensor_native_value(
    pm1_sensor: SinricProAirQualityPM1Sensor,
    mock_air_quality_device: Device,
) -> None:
    """Test PM1 sensor native value."""
    assert pm1_sensor.native_value == mock_air_quality_device.pm1


def test_pm1_sensor_native_value_none_when_no_device(
    pm1_sensor: SinricProAirQualityPM1Sensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test PM1 sensor native value returns None when device not found."""
    mock_coordinator.data = {}
    assert pm1_sensor.native_value is None


# Air Quality PM2.5 Sensor Tests
@pytest.fixture
def pm25_sensor(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_air_quality_device: Device,
) -> SinricProAirQualityPM25Sensor:
    """Create PM2.5 sensor entity."""
    mock_coordinator.data = {mock_air_quality_device.id: mock_air_quality_device}
    return SinricProAirQualityPM25Sensor(
        mock_coordinator, mock_air_quality_device.id, mock_config_entry
    )


def test_pm25_sensor_unique_id(
    pm25_sensor: SinricProAirQualityPM25Sensor,
    mock_config_entry: MagicMock,
    mock_air_quality_device: Device,
) -> None:
    """Test PM2.5 sensor unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_air_quality_device.id}_pm25"
    assert pm25_sensor.unique_id == expected_id


def test_pm25_sensor_name(pm25_sensor: SinricProAirQualityPM25Sensor) -> None:
    """Test PM2.5 sensor name."""
    assert pm25_sensor.name == "PM2.5"


def test_pm25_sensor_device_class(
    pm25_sensor: SinricProAirQualityPM25Sensor,
) -> None:
    """Test PM2.5 sensor device class."""
    assert pm25_sensor.device_class == SensorDeviceClass.PM25


def test_pm25_sensor_native_value(
    pm25_sensor: SinricProAirQualityPM25Sensor,
    mock_air_quality_device: Device,
) -> None:
    """Test PM2.5 sensor native value."""
    assert pm25_sensor.native_value == mock_air_quality_device.pm2_5


# Air Quality PM10 Sensor Tests
@pytest.fixture
def pm10_sensor(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_air_quality_device: Device,
) -> SinricProAirQualityPM10Sensor:
    """Create PM10 sensor entity."""
    mock_coordinator.data = {mock_air_quality_device.id: mock_air_quality_device}
    return SinricProAirQualityPM10Sensor(
        mock_coordinator, mock_air_quality_device.id, mock_config_entry
    )


def test_pm10_sensor_unique_id(
    pm10_sensor: SinricProAirQualityPM10Sensor,
    mock_config_entry: MagicMock,
    mock_air_quality_device: Device,
) -> None:
    """Test PM10 sensor unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_air_quality_device.id}_pm10"
    assert pm10_sensor.unique_id == expected_id


def test_pm10_sensor_name(pm10_sensor: SinricProAirQualityPM10Sensor) -> None:
    """Test PM10 sensor name."""
    assert pm10_sensor.name == "PM10"


def test_pm10_sensor_device_class(
    pm10_sensor: SinricProAirQualityPM10Sensor,
) -> None:
    """Test PM10 sensor device class."""
    assert pm10_sensor.device_class == SensorDeviceClass.PM10


def test_pm10_sensor_native_value(
    pm10_sensor: SinricProAirQualityPM10Sensor,
    mock_air_quality_device: Device,
) -> None:
    """Test PM10 sensor native value."""
    assert pm10_sensor.native_value == mock_air_quality_device.pm10


# Temperature Sensor Tests
@pytest.fixture
def temperature_sensor(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_temperature_device: Device,
) -> SinricProTemperatureSensor:
    """Create temperature sensor entity."""
    mock_coordinator.data = {mock_temperature_device.id: mock_temperature_device}
    return SinricProTemperatureSensor(
        mock_coordinator, mock_temperature_device.id, mock_config_entry
    )


def test_temperature_sensor_unique_id(
    temperature_sensor: SinricProTemperatureSensor,
    mock_config_entry: MagicMock,
    mock_temperature_device: Device,
) -> None:
    """Test temperature sensor unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_temperature_device.id}_temperature"
    assert temperature_sensor.unique_id == expected_id


def test_temperature_sensor_name(
    temperature_sensor: SinricProTemperatureSensor,
) -> None:
    """Test temperature sensor name."""
    assert temperature_sensor.name == "Temperature"


def test_temperature_sensor_device_class(
    temperature_sensor: SinricProTemperatureSensor,
) -> None:
    """Test temperature sensor device class."""
    assert temperature_sensor.device_class == SensorDeviceClass.TEMPERATURE


def test_temperature_sensor_state_class(
    temperature_sensor: SinricProTemperatureSensor,
) -> None:
    """Test temperature sensor state class."""
    assert temperature_sensor.state_class == SensorStateClass.MEASUREMENT


def test_temperature_sensor_unit(
    temperature_sensor: SinricProTemperatureSensor,
) -> None:
    """Test temperature sensor unit."""
    assert temperature_sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS


def test_temperature_sensor_native_value(
    temperature_sensor: SinricProTemperatureSensor,
    mock_temperature_device: Device,
) -> None:
    """Test temperature sensor native value."""
    assert temperature_sensor.native_value == mock_temperature_device.temperature


def test_temperature_sensor_native_value_none_when_no_device(
    temperature_sensor: SinricProTemperatureSensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test temperature sensor native value returns None when device not found."""
    mock_coordinator.data = {}
    assert temperature_sensor.native_value is None


def test_temperature_sensor_device_info(
    temperature_sensor: SinricProTemperatureSensor,
) -> None:
    """Test temperature sensor device info."""
    device_info = temperature_sensor.device_info

    assert device_info["identifiers"] == {(DOMAIN, "temp_123")}
    assert device_info["name"] == "Test Temperature Sensor"
    assert device_info["manufacturer"] == MANUFACTURER
    assert device_info["model"] == "Temperature Sensor"


# Humidity Sensor Tests
@pytest.fixture
def humidity_sensor(
    mock_coordinator: MagicMock,
    mock_config_entry: MagicMock,
    mock_temperature_device: Device,
) -> SinricProHumiditySensor:
    """Create humidity sensor entity."""
    mock_coordinator.data = {mock_temperature_device.id: mock_temperature_device}
    return SinricProHumiditySensor(
        mock_coordinator, mock_temperature_device.id, mock_config_entry
    )


def test_humidity_sensor_unique_id(
    humidity_sensor: SinricProHumiditySensor,
    mock_config_entry: MagicMock,
    mock_temperature_device: Device,
) -> None:
    """Test humidity sensor unique ID."""
    expected_id = f"{mock_config_entry.entry_id}_{mock_temperature_device.id}_humidity"
    assert humidity_sensor.unique_id == expected_id


def test_humidity_sensor_name(humidity_sensor: SinricProHumiditySensor) -> None:
    """Test humidity sensor name."""
    assert humidity_sensor.name == "Humidity"


def test_humidity_sensor_device_class(
    humidity_sensor: SinricProHumiditySensor,
) -> None:
    """Test humidity sensor device class."""
    assert humidity_sensor.device_class == SensorDeviceClass.HUMIDITY


def test_humidity_sensor_state_class(
    humidity_sensor: SinricProHumiditySensor,
) -> None:
    """Test humidity sensor state class."""
    assert humidity_sensor.state_class == SensorStateClass.MEASUREMENT


def test_humidity_sensor_unit(humidity_sensor: SinricProHumiditySensor) -> None:
    """Test humidity sensor unit."""
    assert humidity_sensor.native_unit_of_measurement == PERCENTAGE


def test_humidity_sensor_native_value(
    humidity_sensor: SinricProHumiditySensor,
    mock_temperature_device: Device,
) -> None:
    """Test humidity sensor native value."""
    assert humidity_sensor.native_value == mock_temperature_device.humidity


def test_humidity_sensor_native_value_none_when_no_device(
    humidity_sensor: SinricProHumiditySensor,
    mock_coordinator: MagicMock,
) -> None:
    """Test humidity sensor native value returns None when device not found."""
    mock_coordinator.data = {}
    assert humidity_sensor.native_value is None


def test_humidity_sensor_device_info(
    humidity_sensor: SinricProHumiditySensor,
) -> None:
    """Test humidity sensor device info."""
    device_info = humidity_sensor.device_info

    assert device_info["identifiers"] == {(DOMAIN, "temp_123")}
    assert device_info["name"] == "Test Temperature Sensor"
    assert device_info["manufacturer"] == MANUFACTURER
    assert device_info["model"] == "Temperature Sensor"
