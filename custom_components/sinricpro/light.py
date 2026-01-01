"""Light platform for SinricPro."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.components.light import ATTR_COLOR_TEMP_KELVIN
from homeassistant.components.light import ATTR_RGB_COLOR
from homeassistant.components.light import ColorMode
from homeassistant.components.light import LightEntity
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
from .const import COLOR_TEMP_MAX_KELVIN
from .const import COLOR_TEMP_MIN_KELVIN
from .const import DEVICE_TYPE_DIMMABLE_SWITCH
from .const import DEVICE_TYPE_LIGHT
from .const import DOMAIN
from .const import MANUFACTURER
from .coordinator import SinricProDataUpdateCoordinator
from .exceptions import SinricProDeviceOfflineError
from .exceptions import SinricProError
from .exceptions import SinricProTimeoutError

_LOGGER = logging.getLogger(__name__)

# Timeout for waiting for SSE confirmation (seconds)
PENDING_STATE_TIMEOUT = 10

# Brightness conversion constants
HA_BRIGHTNESS_MAX = 255
SINRIC_BRIGHTNESS_MAX = 100



def sinric_to_ha_brightness(sinric_brightness: int) -> int:
    """Convert SinricPro brightness (0-100) to Home Assistant brightness (0-255)."""
    return round(sinric_brightness * HA_BRIGHTNESS_MAX / SINRIC_BRIGHTNESS_MAX)


def ha_to_sinric_brightness(ha_brightness: int) -> int:
    """Convert Home Assistant brightness (0-255) to SinricPro brightness (0-100)."""
    return round(ha_brightness * SINRIC_BRIGHTNESS_MAX / HA_BRIGHTNESS_MAX)




async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro lights from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Filter for light and dimmable switch devices
    lights = [
        SinricProLight(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type in (DEVICE_TYPE_LIGHT, DEVICE_TYPE_DIMMABLE_SWITCH)
    ]

    _LOGGER.debug("Adding %d light entities", len(lights))
    async_add_entities(lights)


class SinricProLight(CoordinatorEntity[SinricProDataUpdateCoordinator], LightEntity):
    """Representation of a SinricPro light or dimmable switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the light.

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
        self._pending_target_brightness: int | None = None
        self._pending_target_color: tuple[int, int, int] | None = None
        self._pending_target_color_temperature: int | None = None
        self._pending_timeout_cancel: CALLBACK_TYPE | None = None

        # Set supported color modes based on device type
        device = coordinator.data.get(device_id)
        if device and device.device_type == DEVICE_TYPE_DIMMABLE_SWITCH:
            # Dimmable switches only support brightness
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._current_color_mode = ColorMode.BRIGHTNESS
        else:
            # Lights support RGB and color temperature
            self._attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
            self._attr_min_color_temp_kelvin = COLOR_TEMP_MIN_KELVIN
            self._attr_max_color_temp_kelvin = COLOR_TEMP_MAX_KELVIN
            self._current_color_mode = ColorMode.RGB

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def _is_dimmable_switch(self) -> bool:
        """Return True if this is a dimmable switch."""
        device = self._device
        return device is not None and device.device_type == DEVICE_TYPE_DIMMABLE_SWITCH

    @property
    def name(self) -> str | None:
        """Return the name of the light."""
        device = self._device
        if device:
            return device.name
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if the light is on."""
        # Return None (unknown state) while waiting for SSE confirmation
        if self._pending_command:
            return None

        device = self._device
        if device:
            return device.power_state
        return None

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light (0-255)."""
        device = self._device
        if device:
            # For dimmable switches, use power_level; for lights, use brightness
            if self._is_dimmable_switch:
                if device.power_level is not None:
                    return sinric_to_ha_brightness(device.power_level)
            elif device.brightness is not None:
                return sinric_to_ha_brightness(device.brightness)
        return None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color of the light."""
        device = self._device
        if device and device.color is not None:
            return device.color
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        device = self._device
        if device and device.color_temperature is not None:
            return device.color_temperature
        return None

    @property
    def color_mode(self) -> ColorMode:
        """Return the current color mode."""
        return self._current_color_mode

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
        """Return device info for the light."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Light",
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
                # Check if brightness/power_level matches expected
                if self._is_dimmable_switch:
                    brightness_matches = (
                        self._pending_target_brightness is None
                        or device.power_level == self._pending_target_brightness
                    )
                else:
                    brightness_matches = (
                        self._pending_target_brightness is None
                        or device.brightness == self._pending_target_brightness
                    )
                # Check if color matches expected
                color_matches = (
                    self._pending_target_color is None
                    or device.color == self._pending_target_color
                )
                # Check if color temperature matches expected
                color_temp_matches = (
                    self._pending_target_color_temperature is None
                    or device.color_temperature == self._pending_target_color_temperature
                )

                if power_matches and brightness_matches and color_matches and color_temp_matches:
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
        self._pending_target_brightness = None
        self._pending_target_color = None
        self._pending_target_color_temperature = None
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
        """Turn the light on.

        Args:
            **kwargs: Additional arguments (brightness, rgb_color, color_temp, etc.).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        rgb_color = kwargs.get(ATTR_RGB_COLOR)
        color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)

        # Handle color temperature if provided (switches to COLOR_TEMP mode)
        if color_temp_kelvin is not None:
            await self._set_color_temperature(color_temp_kelvin)
            self._current_color_mode = ColorMode.COLOR_TEMP

        # Handle RGB color if provided (switches to RGB mode)
        if rgb_color is not None:
            await self._set_color(rgb_color[0], rgb_color[1], rgb_color[2])
            self._current_color_mode = ColorMode.RGB

        # Handle brightness if provided
        if brightness is not None:
            sinric_brightness = ha_to_sinric_brightness(brightness)
            # Use set_power_level for dimmable switches, set_brightness for lights
            if self._is_dimmable_switch:
                await self._set_power_level(sinric_brightness)
            else:
                await self._set_brightness(sinric_brightness)

        # Turn on if currently off, or if no other attributes specified
        device = self._device
        if device and not device.power_state:
            await self._set_power_state(True)
        elif brightness is None and rgb_color is None and color_temp_kelvin is None:
            # Just turning on with no attributes - set full brightness
            await self._set_power_state(True)
            await self._set_brightness(100)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self._set_power_state(False)

    async def _set_power_state(self, state: bool) -> None:
        """Set the power state of the light.

        Args:
            state: True for on, False for off.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state - light will show as unknown until SSE confirms
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

    async def _set_brightness(self, brightness: int) -> None:
        """Set the brightness of the light.

        Args:
            brightness: Brightness level (0-100).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state
        self._pending_command = True
        self._pending_target_brightness = brightness
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
            await self.coordinator.api.set_brightness(self._device_id, brightness)
            _LOGGER.debug(
                "Brightness command sent for %s to %d, waiting for SSE confirmation",
                self._device_id,
                brightness,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting brightness, retrying once")
            try:
                await self.coordinator.api.set_brightness(self._device_id, brightness)
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

    async def _set_power_level(self, power_level: int) -> None:
        """Set the power level of the dimmable switch.

        Args:
            power_level: Power level (0-100).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state
        self._pending_command = True
        self._pending_target_brightness = power_level
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
            await self.coordinator.api.set_power_level(self._device_id, power_level)
            _LOGGER.debug(
                "Power level command sent for %s to %d, waiting for SSE confirmation",
                self._device_id,
                power_level,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting power level, retrying once")
            try:
                await self.coordinator.api.set_power_level(self._device_id, power_level)
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

    async def _set_color(self, red: int, green: int, blue: int) -> None:
        """Set the color of the light.

        Args:
            red: Red component (0-255).
            green: Green component (0-255).
            blue: Blue component (0-255).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state
        self._pending_command = True
        self._pending_target_color = (red, green, blue)
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
            await self.coordinator.api.set_color(self._device_id, red, green, blue)
            _LOGGER.debug(
                "Color command sent for %s to RGB(%d, %d, %d), waiting for SSE confirmation",
                self._device_id,
                red,
                green,
                blue,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting color, retrying once")
            try:
                await self.coordinator.api.set_color(self._device_id, red, green, blue)
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

    async def _set_color_temperature(self, color_temperature: int) -> None:
        """Set the color temperature of the light.

        Args:
            color_temperature: Color temperature in Kelvin (1000-10000).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Set pending state
        self._pending_command = True
        self._pending_target_color_temperature = color_temperature
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
            await self.coordinator.api.set_color_temperature(
                self._device_id, color_temperature
            )
            _LOGGER.debug(
                "Color temperature command sent for %s to %dK, waiting for SSE confirmation",
                self._device_id,
                color_temperature,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting color temperature, retrying once")
            try:
                await self.coordinator.api.set_color_temperature(
                    self._device_id, color_temperature
                )
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
