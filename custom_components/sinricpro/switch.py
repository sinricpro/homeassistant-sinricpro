"""Switch platform for SinricPro."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device
from .const import DEVICE_TYPE_SWITCH
from .const import DOMAIN
from .const import MANUFACTURER
from .coordinator import SinricProDataUpdateCoordinator
from .exceptions import SinricProDeviceOfflineError
from .exceptions import SinricProError
from .exceptions import SinricProTimeoutError

_LOGGER = logging.getLogger(__name__)

# Timeout for waiting for SSE confirmation (seconds)
PENDING_STATE_TIMEOUT = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro switches from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Filter for switch devices only
    switches = [
        SinricProSwitch(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type == DEVICE_TYPE_SWITCH
    ]

    _LOGGER.debug("Adding %d switch entities", len(switches))
    async_add_entities(switches)


class SinricProSwitch(CoordinatorEntity[SinricProDataUpdateCoordinator], SwitchEntity):
    """Representation of a SinricPro switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}"
        self._pending_command: bool = False
        self._pending_target_state: bool | None = None
        self._pending_timeout_cancel: CALLBACK_TYPE | None = None

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str | None:
        """Return the name of the switch."""
        device = self._device
        if device:
            return device.name
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        # Return None (unknown state) while waiting for SSE confirmation
        if self._pending_command:
            return None

        device = self._device
        if device:
            return device.power_state
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
        """Return device info for the switch."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Switch",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._pending_command:
            device = self._device
            if device and device.power_state == self._pending_target_state:
                # SSE confirmed the state change
                _LOGGER.debug(
                    "SSE confirmed state change for %s to %s",
                    self._device_id,
                    "on" if self._pending_target_state else "off",
                )
                self._clear_pending_state()

        self.async_write_ha_state()

    def _clear_pending_state(self) -> None:
        """Clear the pending command state."""
        self._pending_command = False
        self._pending_target_state = None
        if self._pending_timeout_cancel:
            self._pending_timeout_cancel()
            self._pending_timeout_cancel = None

    @callback
    def _handle_pending_timeout(self, _now: Any) -> None:
        """Handle timeout waiting for SSE confirmation."""
        if self._pending_command:
            _LOGGER.warning(
                "Timeout waiting for SSE confirmation for %s, falling back to API state",
                self._device_id,
            )
            self._clear_pending_state()
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_power_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_power_state(False)

    async def _set_power_state(self, state: bool) -> None:
        """Set the power state of the switch.

        Args:
            state: True for on, False for off.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state - switch will show as unknown until SSE confirms
        self._pending_command = True
        self._pending_target_state = state
        self.async_write_ha_state()

        # Set timeout for SSE confirmation
        self._pending_timeout_cancel = async_call_later(
            self.hass,
            PENDING_STATE_TIMEOUT,
            self._handle_pending_timeout,
        )

        try:
            await self.coordinator.api.set_power_state(self._device_id, state)
            _LOGGER.debug(
                "Command sent for %s to %s, waiting for SSE confirmation",
                self._device_id,
                "on" if state else "off",
            )
            # Don't update state here - wait for SSE to confirm

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            # Retry once
            _LOGGER.debug("Timeout setting power state, retrying once")
            try:
                await self.coordinator.api.set_power_state(self._device_id, state)
            except SinricProError:
                self._clear_pending_state()
                self.async_write_ha_state()
                raise HomeAssistantError(
                    f"Failed to control {self.name}: Request timed out"
                ) from err

        except SinricProError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Failed to control {self.name}: {err}"
            ) from err
