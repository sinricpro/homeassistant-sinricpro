"""Event platform for SinricPro (Doorbell)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.event import EventDeviceClass
from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device
from .const import DEVICE_TYPE_DOORBELL
from .const import DOMAIN
from .const import MANUFACTURER
from .coordinator import SinricProDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

EVENT_TYPE_DOORBELL_PRESSED = "pressed"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro doorbell event entities from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Filter for doorbell devices only
    events = [
        SinricProDoorbellEvent(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type == DEVICE_TYPE_DOORBELL
    ]

    _LOGGER.debug("Adding %d doorbell event entities", len(events))
    async_add_entities(events)


class SinricProDoorbellEvent(
    CoordinatorEntity[SinricProDataUpdateCoordinator], EventEntity
):
    """Representation of a SinricPro doorbell event."""

    _attr_has_entity_name = True
    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types = [EVENT_TYPE_DOORBELL_PRESSED]
    _attr_translation_key = "doorbell"

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the doorbell event entity.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_event"
        self._unregister_callback: callable | None = None

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str | None:
        """Return the name of the event entity."""
        device = self._device
        if device:
            return f"{device.name} Doorbell"
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
        """Return device info for the doorbell."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Doorbell",
        )

    async def async_added_to_hass(self) -> None:
        """Register doorbell callback when entity is added."""
        await super().async_added_to_hass()

        @callback
        def _handle_doorbell_press(timestamp: str) -> None:
            """Handle doorbell press event."""
            _LOGGER.debug(
                "Doorbell pressed event received for %s at %s",
                self._device_id,
                timestamp,
            )
            self._trigger_event(
                EVENT_TYPE_DOORBELL_PRESSED,
                {"timestamp": timestamp},
            )
            self.async_write_ha_state()

        self._unregister_callback = self.coordinator.register_doorbell_callback(
            self._device_id, _handle_doorbell_press
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister doorbell callback when entity is removed."""
        if self._unregister_callback:
            self._unregister_callback()
            self._unregister_callback = None
        await super().async_will_remove_from_hass()
