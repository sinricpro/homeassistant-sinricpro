"""Lock platform for SinricPro."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity
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
from .const import DEVICE_TYPE_SMARTLOCK
from .const import DOMAIN
from .const import LOCK_ACTION_LOCK
from .const import LOCK_ACTION_UNLOCK
from .const import LOCK_STATE_LOCKED
from .const import LOCK_STATE_UNLOCKED
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
    """Set up SinricPro locks from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Filter for lock devices only
    locks = [
        SinricProLock(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type == DEVICE_TYPE_SMARTLOCK
    ]

    _LOGGER.debug("Adding %d lock entities", len(locks))
    async_add_entities(locks)


class SinricProLock(CoordinatorEntity[SinricProDataUpdateCoordinator], LockEntity):
    """Representation of a SinricPro lock."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the lock.

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
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str | None:
        """Return the name of the lock."""
        device = self._device
        if device:
            return device.name
        return None

    @property
    def is_locked(self) -> bool | None:
        """Return True if the lock is locked."""
        # Return None (unknown state) while waiting for SSE confirmation
        if self._pending_command:
            return None

        device = self._device
        if device and device.lock_state is not None:
            return device.lock_state == LOCK_STATE_LOCKED
        return None

    @property
    def is_locking(self) -> bool:
        """Return True if the lock is locking."""
        if self._pending_command:
            return self._pending_target_state == LOCK_STATE_LOCKED
        return False

    @property
    def is_unlocking(self) -> bool:
        """Return True if the lock is unlocking."""
        if self._pending_command:
            return self._pending_target_state != LOCK_STATE_LOCKED
        return False

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
        """Return device info for the lock."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Smart Lock",
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
                    or device.lock_state == self._pending_target_state
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

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_lock_state(True)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_lock_state(False)

    async def _set_lock_state(self, locked: bool) -> None:
        """Set the lock state.

        Args:
            locked: True to lock, False to unlock.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Determine the action and expected state
        action = LOCK_ACTION_LOCK if locked else LOCK_ACTION_UNLOCK
        expected_state = LOCK_STATE_LOCKED if locked else LOCK_STATE_UNLOCKED

        # Set pending state - lock will show as unknown until SSE confirms
        self._pending_command = True
        self._pending_target_state = expected_state
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
            await self.coordinator.api.set_lock_state(self._device_id, action)
            _LOGGER.debug(
                "Lock command sent for %s to %s, waiting for SSE confirmation",
                self._device_id,
                action,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting lock state, retrying once")
            try:
                await self.coordinator.api.set_lock_state(self._device_id, action)
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
