"""Sensor platform for SinricPro (Doorbell, Air Quality)."""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
from homeassistant.const import PERCENTAGE
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device
from .const import DEVICE_TYPE_AIR_QUALITY_SENSOR
from .const import DEVICE_TYPE_DOORBELL
from .const import DEVICE_TYPE_TEMPERATURE_SENSOR
from .const import DOMAIN
from .const import MANUFACTURER
from .coordinator import SinricProDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro sensor entities from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors: list[SensorEntity] = []

    # Filter for doorbell devices and create last ring sensors
    sensors.extend([
        SinricProDoorbellLastRingSensor(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type == DEVICE_TYPE_DOORBELL
    ])

    # Filter for air quality sensors and create PM sensors
    for device_id, device in coordinator.data.items():
        if device.device_type == DEVICE_TYPE_AIR_QUALITY_SENSOR:
            sensors.extend([
                SinricProAirQualityPM1Sensor(coordinator, device_id, entry),
                SinricProAirQualityPM25Sensor(coordinator, device_id, entry),
                SinricProAirQualityPM10Sensor(coordinator, device_id, entry),
            ])

    # Filter for temperature sensors and create temperature/humidity sensors
    for device_id, device in coordinator.data.items():
        if device.device_type == DEVICE_TYPE_TEMPERATURE_SENSOR:
            sensors.extend([
                SinricProTemperatureSensor(coordinator, device_id, entry),
                SinricProHumiditySensor(coordinator, device_id, entry),
            ])

    _LOGGER.debug("Adding %d sensor entities", len(sensors))
    async_add_entities(sensors)


class SinricProDoorbellLastRingSensor(
    CoordinatorEntity[SinricProDataUpdateCoordinator], SensorEntity
):
    """Representation of a SinricPro doorbell last ring timestamp sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the doorbell last ring sensor.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_last_ring"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str:
        """Return the name of the sensor entity."""
        return "Last Ring"

    @property
    def native_value(self) -> datetime | None:
        """Return the last doorbell ring timestamp."""
        device = self._device
        if device and device.last_doorbell_ring:
            try:
                return datetime.fromisoformat(
                    device.last_doorbell_ring.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                _LOGGER.warning(
                    "Failed to parse last_doorbell_ring timestamp: %s",
                    device.last_doorbell_ring,
                )
                return None
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return self.coordinator.last_update_success and device is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the doorbell."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Doorbell",
        )


class SinricProAirQualityPM1Sensor(
    CoordinatorEntity[SinricProDataUpdateCoordinator], SensorEntity
):
    """Representation of a SinricPro air quality PM1.0 sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.PM1
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the PM1.0 sensor.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_pm1"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str:
        """Return the name of the sensor entity."""
        return "PM1.0"

    @property
    def native_value(self) -> float | None:
        """Return the PM1.0 value."""
        device = self._device
        if device:
            return device.pm1
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return (
            self.coordinator.last_update_success
            and device is not None
            and device.is_online
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the air quality sensor."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Air Quality Sensor",
        )


class SinricProAirQualityPM25Sensor(
    CoordinatorEntity[SinricProDataUpdateCoordinator], SensorEntity
):
    """Representation of a SinricPro air quality PM2.5 sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.PM25
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the PM2.5 sensor.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_pm25"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str:
        """Return the name of the sensor entity."""
        return "PM2.5"

    @property
    def native_value(self) -> float | None:
        """Return the PM2.5 value."""
        device = self._device
        if device:
            return device.pm2_5
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return (
            self.coordinator.last_update_success
            and device is not None
            and device.is_online
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the air quality sensor."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Air Quality Sensor",
        )


class SinricProAirQualityPM10Sensor(
    CoordinatorEntity[SinricProDataUpdateCoordinator], SensorEntity
):
    """Representation of a SinricPro air quality PM10 sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.PM10
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the PM10 sensor.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_pm10"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str:
        """Return the name of the sensor entity."""
        return "PM10"

    @property
    def native_value(self) -> float | None:
        """Return the PM10 value."""
        device = self._device
        if device:
            return device.pm10
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return (
            self.coordinator.last_update_success
            and device is not None
            and device.is_online
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the air quality sensor."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Air Quality Sensor",
        )


class SinricProTemperatureSensor(
    CoordinatorEntity[SinricProDataUpdateCoordinator], SensorEntity
):
    """Representation of a SinricPro temperature sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the temperature sensor.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_temperature"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str:
        """Return the name of the sensor entity."""
        return "Temperature"

    @property
    def native_value(self) -> float | None:
        """Return the temperature value."""
        device = self._device
        if device:
            return device.temperature
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return (
            self.coordinator.last_update_success
            and device is not None
            and device.is_online
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the temperature sensor."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Temperature Sensor",
        )


class SinricProHumiditySensor(
    CoordinatorEntity[SinricProDataUpdateCoordinator], SensorEntity
):
    """Representation of a SinricPro humidity sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the humidity sensor.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_humidity"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str:
        """Return the name of the sensor entity."""
        return "Humidity"

    @property
    def native_value(self) -> float | None:
        """Return the humidity value."""
        device = self._device
        if device:
            return device.humidity
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return (
            self.coordinator.last_update_success
            and device is not None
            and device.is_online
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the humidity sensor."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Temperature Sensor",
        )
