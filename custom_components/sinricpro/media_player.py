"""Media Player platform for SinricPro (Speakers)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.components.media_player import MediaPlayerState
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
from .const import DEVICE_TYPE_SPEAKER
from .const import DEVICE_TYPE_TV
from .const import DOMAIN
from .const import MANUFACTURER
from .coordinator import SinricProDataUpdateCoordinator
from .exceptions import (
    SinricProDeviceOfflineError,
    SinricProError,
    SinricProTimeoutError,
)

_LOGGER = logging.getLogger(__name__)

# Timeout for waiting for SSE confirmation (seconds)
PENDING_STATE_TIMEOUT = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro speakers from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Filter for speaker and TV devices
    media_players = [
        SinricProSpeaker(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type in (DEVICE_TYPE_SPEAKER, DEVICE_TYPE_TV)
    ]

    _LOGGER.debug("Adding %d media player entities", len(media_players))
    async_add_entities(media_players)


class SinricProSpeaker(
    CoordinatorEntity[SinricProDataUpdateCoordinator], MediaPlayerEntity
):
    """Representation of a SinricPro speaker or TV."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the media player.

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
        self._pending_target_volume: int | None = None
        self._pending_target_muted: bool | None = None
        self._pending_timeout_cancel: CALLBACK_TYPE | None = None

        # Set supported features based on device type
        device = coordinator.data.get(device_id)
        if device and device.device_type == DEVICE_TYPE_TV:
            # TVs support all features including channel navigation and playback
            self._attr_supported_features = (
                MediaPlayerEntityFeature.TURN_ON
                | MediaPlayerEntityFeature.TURN_OFF
                | MediaPlayerEntityFeature.VOLUME_SET
                | MediaPlayerEntityFeature.VOLUME_MUTE
                | MediaPlayerEntityFeature.NEXT_TRACK
                | MediaPlayerEntityFeature.PREVIOUS_TRACK
                | MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.PAUSE
            )
        else:
            # Speakers only support basic features
            self._attr_supported_features = (
                MediaPlayerEntityFeature.TURN_ON
                | MediaPlayerEntityFeature.TURN_OFF
                | MediaPlayerEntityFeature.VOLUME_SET
                | MediaPlayerEntityFeature.VOLUME_MUTE
            )

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def name(self) -> str | None:
        """Return the name of the speaker."""
        device = self._device
        if device:
            return device.name
        return None

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the speaker."""
        # Return None (unknown state) while waiting for SSE confirmation
        if self._pending_command and self._pending_target_state is not None:
            return None

        device = self._device
        if device:
            return MediaPlayerState.ON if device.power_state else MediaPlayerState.OFF
        return None

    @property
    def volume_level(self) -> float | None:
        """Return the volume level (0.0 to 1.0)."""
        device = self._device
        if device and device.volume is not None:
            return device.volume / 100.0
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Return True if volume is muted."""
        device = self._device
        if device:
            return device.is_muted
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
        """Return device info for the speaker."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Speaker",
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
                # Check if volume matches expected
                volume_matches = (
                    self._pending_target_volume is None
                    or device.volume == self._pending_target_volume
                )
                # Check if mute state matches expected
                mute_matches = (
                    self._pending_target_muted is None
                    or device.is_muted == self._pending_target_muted
                )

                if power_matches and volume_matches and mute_matches:
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
        self._pending_target_volume = None
        self._pending_target_muted = None
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

    async def async_turn_on(self) -> None:
        """Turn the speaker on.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_power_state(True)

    async def async_turn_off(self) -> None:
        """Turn the speaker off.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_power_state(False)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume level (0.0 to 1.0).

        Args:
            volume: Volume level (0.0 to 1.0).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        volume_int = int(volume * 100)
        await self._set_volume(volume_int)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the speaker.

        Args:
            mute: True to mute, False to unmute.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_mute(mute)

    async def async_media_next_track(self) -> None:
        """Send next track command (channel up for TV).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        try:
            await self.coordinator.api.skip_channels(self._device_id, 1)
            _LOGGER.debug("Channel up command sent for %s", self._device_id)

        except SinricProDeviceOfflineError as err:
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProError as err:
            raise HomeAssistantError(
                f"Failed to control {self.name}: {err}"
            ) from err

    async def async_media_previous_track(self) -> None:
        """Send previous track command (channel down for TV).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        try:
            await self.coordinator.api.skip_channels(self._device_id, -1)
            _LOGGER.debug("Channel down command sent for %s", self._device_id)

        except SinricProDeviceOfflineError as err:
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProError as err:
            raise HomeAssistantError(
                f"Failed to control {self.name}: {err}"
            ) from err

    async def async_media_play(self) -> None:
        """Send play command to TV.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        try:
            await self.coordinator.api.media_control(self._device_id, "play")
            _LOGGER.debug("Play command sent for %s", self._device_id)

        except SinricProDeviceOfflineError as err:
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProError as err:
            raise HomeAssistantError(
                f"Failed to control {self.name}: {err}"
            ) from err

    async def async_media_pause(self) -> None:
        """Send pause command to TV.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        try:
            await self.coordinator.api.media_control(self._device_id, "pause")
            _LOGGER.debug("Pause command sent for %s", self._device_id)

        except SinricProDeviceOfflineError as err:
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProError as err:
            raise HomeAssistantError(
                f"Failed to control {self.name}: {err}"
            ) from err

    async def _set_power_state(self, state: bool) -> None:
        """Set the power state of the speaker.

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
                "Power command sent for %s to %s, waiting for SSE confirmation",
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

    async def _set_volume(self, volume: int) -> None:
        """Set the volume of the speaker.

        Args:
            volume: Volume level (0-100).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state
        self._pending_command = True
        self._pending_target_volume = volume
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
            await self.coordinator.api.set_volume(self._device_id, volume)
            _LOGGER.debug(
                "Volume command sent for %s to %d, waiting for SSE confirmation",
                self._device_id,
                volume,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting volume, retrying once")
            try:
                await self.coordinator.api.set_volume(self._device_id, volume)
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

    async def _set_mute(self, muted: bool) -> None:
        """Set the mute state of the speaker.

        Args:
            muted: True to mute, False to unmute.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state
        self._pending_command = True
        self._pending_target_muted = muted
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
            await self.coordinator.api.set_mute(self._device_id, muted)
            _LOGGER.debug(
                "Mute command sent for %s to %s, waiting for SSE confirmation",
                self._device_id,
                muted,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting mute state, retrying once")
            try:
                await self.coordinator.api.set_mute(self._device_id, muted)
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
