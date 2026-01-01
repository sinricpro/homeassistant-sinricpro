"""Fan platform for SinricPro."""
from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.fan import FanEntity
from homeassistant.components.fan import FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import percentage_to_ranged_value
from homeassistant.util.percentage import ranged_value_to_percentage

from .api import Device
from .const import DEVICE_TYPE_FAN
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
    """Set up SinricPro fans from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Filter for fan devices only
    fans = [
        SinricProFan(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type == DEVICE_TYPE_FAN
    ]

    _LOGGER.debug("Adding %d fan entities", len(fans))
    async_add_entities(fans)


class SinricProFan(CoordinatorEntity[SinricProDataUpdateCoordinator], FanEntity):
    """Representation of a SinricPro fan."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the fan.

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
        self._pending_target_speed: int | None = None
        self._pending_timeout_cancel: CALLBACK_TYPE | None = None

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def _speed_range(self) -> tuple[int, int]:
        """Get the speed range (min, max) for the fan."""
        device = self._device
        max_speed = device.max_fan_speed if device and device.max_fan_speed else 3
        return (1, max_speed)

    @property
    def name(self) -> str | None:
        """Return the name of the fan."""
        device = self._device
        if device:
            return device.name
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if the fan is on."""
        # Return None (unknown state) while waiting for SSE confirmation
        if self._pending_command and self._pending_target_state is not None:
            return None

        device = self._device
        if device:
            return device.power_state
        return None

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        device = self._device
        if device and device.range_value is not None:
            return ranged_value_to_percentage(self._speed_range, device.range_value)
        return None

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return self._speed_range[1]

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
        """Return device info for the fan."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Fan",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._pending_command:
            device = self._device
            if device:
                # Check if power state matches expected
                power_matches = (
                    self._pending_target_state is None
                    or device.power_state == self._pending_target_state
                )
                # Check if speed matches expected
                speed_matches = (
                    self._pending_target_speed is None
                    or device.range_value == self._pending_target_speed
                )

                if power_matches and speed_matches:
                    _LOGGER.debug(
                        "SSE confirmed state change for %s",
                        self._device_id,
                    )
                    self._clear_pending_state()

        self.async_write_ha_state()

    def _clear_pending_state(self) -> None:
        """Clear the pending command state."""
        self._pending_command = False
        self._pending_target_state = None
        self._pending_target_speed = None
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

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on.

        Args:
            percentage: Speed percentage (optional).
            preset_mode: Preset mode (not used).
            **kwargs: Additional arguments.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        if percentage is not None:
            await self._set_percentage(percentage)

        await self._set_power_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_power_state(False)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage.

        Args:
            percentage: Speed percentage (0-100).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        if percentage == 0:
            await self.async_turn_off()
        else:
            await self._set_percentage(percentage)
            # Turn on if not already on
            device = self._device
            if device and not device.power_state:
                await self._set_power_state(True)

    async def _set_power_state(self, state: bool) -> None:
        """Set the power state of the fan.

        Args:
            state: True for on, False for off.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state
        self._pending_command = True
        self._pending_target_state = state
        self.async_write_ha_state()

        # Set timeout for SSE confirmation
        if self._pending_timeout_cancel:
            self._pending_timeout_cancel()
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

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
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

    async def _set_percentage(self, percentage: int) -> None:
        """Set the speed percentage.

        Args:
            percentage: Speed percentage (0-100).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Convert percentage to speed level (1-max)
        speed = math.ceil(percentage_to_ranged_value(self._speed_range, percentage))
        # Ensure minimum speed is 1
        speed = max(1, speed)

        # Set pending state
        self._pending_command = True
        self._pending_target_speed = speed
        self.async_write_ha_state()

        # Set timeout for SSE confirmation
        if self._pending_timeout_cancel:
            self._pending_timeout_cancel()
        self._pending_timeout_cancel = async_call_later(
            self.hass,
            PENDING_STATE_TIMEOUT,
            self._handle_pending_timeout,
        )

        try:
            await self.coordinator.api.set_range_value(self._device_id, speed)
            _LOGGER.debug(
                "Speed command sent for %s to %d (percentage: %d), waiting for SSE confirmation",
                self._device_id,
                speed,
                percentage,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting speed, retrying once")
            try:
                await self.coordinator.api.set_range_value(self._device_id, speed)
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
