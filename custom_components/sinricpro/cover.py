"""Cover platform for SinricPro (Blinds and Garage Doors)."""

from __future__ import annotations

import logging
from typing import Any
from typing import cast

from homeassistant.components.cover import ATTR_POSITION
from homeassistant.components.cover import CoverDeviceClass
from homeassistant.components.cover import CoverEntity
from homeassistant.components.cover import CoverEntityFeature
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
from .const import DEVICE_TYPE_BLIND
from .const import DEVICE_TYPE_GARAGE_DOOR
from .const import DOMAIN
from .const import GARAGE_DOOR_MODE_CLOSE
from .const import GARAGE_DOOR_MODE_OPEN
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
    """Set up SinricPro covers (blinds and garage doors) from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[CoverEntity] = []

    # Add blind covers
    for device_id, device in coordinator.data.items():
        if device.device_type == DEVICE_TYPE_BLIND:
            entities.append(SinricProCover(coordinator, device_id, entry))
        elif device.device_type == DEVICE_TYPE_GARAGE_DOOR:
            entities.append(SinricProGarageDoor(coordinator, device_id, entry))

    _LOGGER.debug("Adding %d cover entities", len(entities))
    async_add_entities(entities)


class SinricProCover(CoordinatorEntity[SinricProDataUpdateCoordinator], CoverEntity):
    """Representation of a SinricPro cover (blind)."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the cover.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}"
        self._pending_command: bool = False
        self._pending_target_position: int | None = None
        self._pending_timeout_cancel: CALLBACK_TYPE | None = None

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return cast(Device | None, self.coordinator.data.get(self._device_id))

    @property
    def name(self) -> str | None:
        """Return the name of the cover."""
        return None

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover (0-100).

        0 is closed, 100 is fully open.
        """
        device = self._device
        if device and device.range_value is not None:
            return device.range_value
        return None

    @property
    def is_closed(self) -> bool | None:
        """Return True if the cover is closed."""
        # Return None (unknown state) while waiting for SSE confirmation
        if self._pending_command:
            return None

        device = self._device
        if device and device.range_value is not None:
            return device.range_value == 0
        return None

    @property
    def is_opening(self) -> bool:
        """Return True if the cover is opening."""
        if self._pending_command and self._pending_target_position is not None:
            device = self._device
            if device and device.range_value is not None:
                return self._pending_target_position > device.range_value
        return False

    @property
    def is_closing(self) -> bool:
        """Return True if the cover is closing."""
        if self._pending_command and self._pending_target_position is not None:
            device = self._device
            if device and device.range_value is not None:
                return self._pending_target_position < device.range_value
        return False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return self.coordinator.last_update_success and device is not None and device.is_online

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the cover."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Blind",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._pending_command:
            device = self._device
            if device:
                # Check if position matches expected
                position_matches = (
                    self._pending_target_position is None
                    or device.range_value == self._pending_target_position
                )

                if position_matches:
                    _LOGGER.debug(
                        "SSE confirmed position change for %s",
                        self._device_id,
                    )
                    self._clear_pending_state()

        self.async_write_ha_state()

    def _clear_pending_state(self) -> None:
        """Clear the pending command state."""
        self._pending_command = False
        self._pending_target_position = None
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

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_position(100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_position(0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover position.

        Args:
            **kwargs: Additional arguments (position).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        position = kwargs.get(ATTR_POSITION)
        if position is not None:
            await self._set_position(position)

    async def _set_position(self, position: int) -> None:
        """Set the position of the cover.

        Args:
            position: Position (0-100). 0 = closed, 100 = open.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state - cover will show as unknown until SSE confirms
        self._pending_command = True
        self._pending_target_position = position
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
            await self.coordinator.api.set_range_value(self._device_id, position)
            _LOGGER.debug(
                "Position command sent for %s to %d, waiting for SSE confirmation",
                self._device_id,
                position,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting position, retrying once")
            try:
                await self.coordinator.api.set_range_value(self._device_id, position)
            except SinricProError:
                self._clear_pending_state()
                self.async_write_ha_state()
                raise HomeAssistantError(
                    f"Failed to control {self.name}: Request timed out"
                ) from err

        except SinricProError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to control {self.name}: {err}") from err


class SinricProGarageDoor(CoordinatorEntity[SinricProDataUpdateCoordinator], CoverEntity):
    """Representation of a SinricPro garage door."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the garage door.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}"
        self._pending_command: bool = False
        self._pending_target_state: str | None = None
        self._pending_timeout_cancel: CALLBACK_TYPE | None = None

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return cast(Device | None, self.coordinator.data.get(self._device_id))

    @property
    def name(self) -> str | None:
        """Return the name of the garage door."""
        return None

    @property
    def is_closed(self) -> bool | None:
        """Return True if the garage door is closed."""
        # Return None (unknown state) while waiting for SSE confirmation
        if self._pending_command:
            return None

        device = self._device
        if device and device.garage_door_state is not None:
            return device.garage_door_state == GARAGE_DOOR_MODE_CLOSE
        return None

    @property
    def is_opening(self) -> bool:
        """Return True if the garage door is opening."""
        if self._pending_command:
            return self._pending_target_state == GARAGE_DOOR_MODE_OPEN
        return False

    @property
    def is_closing(self) -> bool:
        """Return True if the garage door is closing."""
        if self._pending_command:
            return self._pending_target_state == GARAGE_DOOR_MODE_CLOSE
        return False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return self.coordinator.last_update_success and device is not None and device.is_online

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the garage door."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Garage Door",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._pending_command:
            device = self._device
            if device:
                # Check if state matches expected
                state_matches = (
                    self._pending_target_state is None
                    or device.garage_door_state == self._pending_target_state
                )

                if state_matches:
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

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the garage door.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_mode(GARAGE_DOOR_MODE_OPEN)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the garage door.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_mode(GARAGE_DOOR_MODE_CLOSE)

    async def _set_mode(self, mode: str) -> None:
        """Set the mode of the garage door.

        Args:
            mode: Mode ("Open" or "Close").

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state - garage door will show as unknown until SSE confirms
        self._pending_command = True
        self._pending_target_state = mode
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
            await self.coordinator.api.set_mode(self._device_id, mode)
            _LOGGER.debug(
                "Mode command sent for %s to %s, waiting for SSE confirmation",
                self._device_id,
                mode,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting mode, retrying once")
            try:
                await self.coordinator.api.set_mode(self._device_id, mode)
            except SinricProError:
                self._clear_pending_state()
                self.async_write_ha_state()
                raise HomeAssistantError(
                    f"Failed to control {self.name}: Request timed out"
                ) from err

        except SinricProError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to control {self.name}: {err}") from err
