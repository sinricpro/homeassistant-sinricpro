"""Binary Sensor platform for SinricPro (Contact, Motion)."""

from __future__ import annotations

import logging
from typing import cast

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device
from .const import DEVICE_TYPE_CONTACT_SENSOR
from .const import DEVICE_TYPE_MOTION_SENSOR
from .const import DOMAIN
from .const import MANUFACTURER
from .coordinator import SinricProDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro binary sensor entities from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    binary_sensors: list[BinarySensorEntity] = []

    # Filter for contact sensors
    binary_sensors.extend(
        [
            SinricProContactSensor(coordinator, device_id, entry)
            for device_id, device in coordinator.data.items()
            if device.device_type == DEVICE_TYPE_CONTACT_SENSOR
        ]
    )

    # Filter for motion sensors
    binary_sensors.extend(
        [
            SinricProMotionSensor(coordinator, device_id, entry)
            for device_id, device in coordinator.data.items()
            if device.device_type == DEVICE_TYPE_MOTION_SENSOR
        ]
    )

    _LOGGER.debug("Adding %d binary sensor entities", len(binary_sensors))
    async_add_entities(binary_sensors)


class SinricProContactSensor(CoordinatorEntity[SinricProDataUpdateCoordinator], BinarySensorEntity):
    """Representation of a SinricPro contact sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the contact sensor.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return cast(Device | None, self.coordinator.data.get(self._device_id))

    @property
    def name(self) -> str | None:
        """Return the name of the sensor entity."""
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if contact is open."""
        device = self._device
        if device and device.contact_state:
            return device.contact_state == "open"
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return self.coordinator.last_update_success and device is not None and device.is_online

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the contact sensor."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Contact Sensor",
        )


class SinricProMotionSensor(CoordinatorEntity[SinricProDataUpdateCoordinator], BinarySensorEntity):
    """Representation of a SinricPro motion sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the motion sensor.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return cast(Device | None, self.coordinator.data.get(self._device_id))

    @property
    def name(self) -> str | None:
        """Return the name of the sensor entity."""
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if motion is detected."""
        device = self._device
        if device and device.last_motion_state:
            return device.last_motion_state == "detected"
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return self.coordinator.last_update_success and device is not None and device.is_online

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the motion sensor."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Motion Sensor",
        )
