"""Button platform for SinricPro (Doorbell trigger)."""

from __future__ import annotations

import logging
from typing import cast

from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device
from .const import DEVICE_TYPE_DOORBELL
from .const import DOMAIN
from .const import MANUFACTURER
from .coordinator import SinricProDataUpdateCoordinator
from .exceptions import SinricProDeviceOfflineError
from .exceptions import SinricProError
from .exceptions import SinricProTimeoutError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro doorbell button entities from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Filter for doorbell devices only
    buttons = [
        SinricProDoorbellButton(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type == DEVICE_TYPE_DOORBELL
    ]

    _LOGGER.debug("Adding %d doorbell button entities", len(buttons))
    async_add_entities(buttons)


class SinricProDoorbellButton(CoordinatorEntity[SinricProDataUpdateCoordinator], ButtonEntity):
    """Representation of a SinricPro doorbell button."""

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.IDENTIFY

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the doorbell button entity.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_button"

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return cast(Device | None, self.coordinator.data.get(self._device_id))

    @property
    def name(self) -> str | None:
        """Return the name of the button entity."""
        device = self._device
        if device:
            return "Ring"
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return self.coordinator.last_update_success and device is not None and device.is_online

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

    async def async_press(self) -> None:
        """Handle the button press.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        try:
            await self.coordinator.api.press_doorbell(self._device_id)
            _LOGGER.debug(
                "Doorbell press command sent for %s",
                self._device_id,
            )

        except SinricProDeviceOfflineError as err:
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout pressing doorbell, retrying once")
            try:
                await self.coordinator.api.press_doorbell(self._device_id)
            except SinricProError:
                raise HomeAssistantError(
                    f"Failed to control {self.name}: Request timed out"
                ) from err

        except SinricProError as err:
            raise HomeAssistantError(f"Failed to control {self.name}: {err}") from err
