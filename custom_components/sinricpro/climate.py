"""Climate platform for SinricPro (Thermostats)."""

from __future__ import annotations

import logging
from typing import Any
from typing import ClassVar
from typing import cast

from homeassistant.components.climate import FAN_HIGH
from homeassistant.components.climate import FAN_LOW
from homeassistant.components.climate import FAN_MEDIUM
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.const import UnitOfTemperature
from homeassistant.core import CALLBACK_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device
from .const import DEVICE_TYPE_AC_UNIT
from .const import DEVICE_TYPE_THERMOSTAT
from .const import DOMAIN
from .const import MANUFACTURER
from .coordinator import SinricProDataUpdateCoordinator
from .exceptions import SinricProDeviceOfflineError
from .exceptions import SinricProError
from .exceptions import SinricProTimeoutError

_LOGGER = logging.getLogger(__name__)

# Timeout for waiting for SSE confirmation (seconds)
PENDING_STATE_TIMEOUT = 10

# SinricPro to Home Assistant HVAC mode mapping
SINRIC_TO_HA_HVAC_MODE = {
    "COOL": HVACMode.COOL,
    "HEAT": HVACMode.HEAT,
    "AUTO": HVACMode.AUTO,
    "ECO": HVACMode.AUTO,  # Map ECO to AUTO for AC units
    "OFF": HVACMode.OFF,
}

# Home Assistant to SinricPro HVAC mode mapping
HA_TO_SINRIC_HVAC_MODE = {
    HVACMode.COOL: "COOL",
    HVACMode.HEAT: "HEAT",
    HVACMode.AUTO: "AUTO",
    HVACMode.OFF: "OFF",
}

# Fan mode mappings (for AC units)
SINRIC_TO_HA_FAN_MODE = {
    1: FAN_LOW,
    2: FAN_MEDIUM,
    3: FAN_HIGH,
}

HA_TO_SINRIC_FAN_MODE = {
    FAN_LOW: 1,
    FAN_MEDIUM: 2,
    FAN_HIGH: 3,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro thermostats from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Filter for thermostat and AC unit devices
    climate_devices = [
        SinricProThermostat(coordinator, device_id, entry)
        for device_id, device in coordinator.data.items()
        if device.device_type in (DEVICE_TYPE_THERMOSTAT, DEVICE_TYPE_AC_UNIT)
    ]

    _LOGGER.debug("Adding %d climate entities", len(climate_devices))
    async_add_entities(climate_devices)


class SinricProThermostat(CoordinatorEntity[SinricProDataUpdateCoordinator], ClimateEntity):
    """Representation of a SinricPro thermostat or AC unit."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes: ClassVar[list[HVACMode]] = [  # type: ignore[misc]
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.AUTO,
    ]

    def __init__(
        self,
        coordinator: SinricProDataUpdateCoordinator,
        device_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the thermostat or AC unit.

        Args:
            coordinator: Data update coordinator.
            device_id: SinricPro device ID.
            entry: Config entry.
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_{device_id}"
        self._pending_command: bool = False
        self._pending_target_temperature: float | None = None
        self._pending_hvac_mode: HVACMode | None = None
        self._pending_fan_mode: str | None = None
        self._pending_timeout_cancel: CALLBACK_TYPE | None = None

        # Check if device is AC unit
        device = coordinator.data.get(device_id)
        self._is_ac_unit = device and device.device_type == DEVICE_TYPE_AC_UNIT

        # Set supported features based on device type
        if self._is_ac_unit:
            self._attr_supported_features = (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.TURN_ON
                | ClimateEntityFeature.TURN_OFF
                | ClimateEntityFeature.FAN_MODE
            )
            self._attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH]
        else:
            self._attr_supported_features = (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.TURN_ON
                | ClimateEntityFeature.TURN_OFF
            )
            self._attr_fan_modes = None

    @property
    def _device(self) -> Device | None:
        """Get the device from coordinator data."""
        if self.coordinator.data is None:
            return None
        return cast(Device | None, self.coordinator.data.get(self._device_id))

    @property
    def name(self) -> str | None:
        """Return the name of the thermostat."""
        device = self._device
        if device:
            return device.name
        return None

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        # Return None (unknown state) while waiting for SSE confirmation
        if self._pending_command and self._pending_hvac_mode is not None:
            return None

        device = self._device
        if device and device.thermostat_mode:
            return SINRIC_TO_HA_HVAC_MODE.get(device.thermostat_mode, HVACMode.OFF)
        return HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        device = self._device
        if device:
            return device.temperature
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        device = self._device
        if device:
            return device.target_temperature
        return None

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        device = self._device
        if device and device.humidity is not None:
            return int(device.humidity)
        return None

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode (AC units only)."""
        if not self._is_ac_unit:
            return None

        device = self._device
        if device and device.range_value is not None:
            return SINRIC_TO_HA_FAN_MODE.get(device.range_value)
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        device = self._device
        return self.coordinator.last_update_success and device is not None and device.is_online

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the thermostat."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else self._device_id,
            manufacturer=MANUFACTURER,
            model="Thermostat",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._pending_command:
            device = self._device
            if device:
                # Check if HVAC mode matches expected
                hvac_mode_matches = True
                if self._pending_hvac_mode is not None:
                    expected_sinric_mode = HA_TO_SINRIC_HVAC_MODE.get(self._pending_hvac_mode)
                    hvac_mode_matches = device.thermostat_mode == expected_sinric_mode

                # Check if target temperature matches expected
                temp_matches = (
                    self._pending_target_temperature is None
                    or device.target_temperature == self._pending_target_temperature
                )

                # Check if fan mode matches expected (AC units only)
                fan_mode_matches = True
                if self._pending_fan_mode is not None and self._is_ac_unit:
                    expected_range_value = HA_TO_SINRIC_FAN_MODE.get(self._pending_fan_mode)
                    fan_mode_matches = device.range_value == expected_range_value

                if hvac_mode_matches and temp_matches and fan_mode_matches:
                    _LOGGER.debug(
                        "SSE confirmed state change for %s",
                        self._device_id,
                    )
                    self._clear_pending_state()

        self.async_write_ha_state()

    def _clear_pending_state(self) -> None:
        """Clear the pending command state."""
        self._pending_command = False
        self._pending_target_temperature = None
        self._pending_hvac_mode = None
        self._pending_fan_mode = None
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

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode.

        Args:
            hvac_mode: HVAC mode to set.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        if hvac_mode not in HA_TO_SINRIC_HVAC_MODE:
            raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")

        sinric_mode = HA_TO_SINRIC_HVAC_MODE[hvac_mode]

        # Set pending state
        self._pending_command = True
        self._pending_hvac_mode = hvac_mode
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
            await self.coordinator.api.set_thermostat_mode(self._device_id, sinric_mode)
            _LOGGER.debug(
                "Thermostat mode command sent for %s to %s, waiting for SSE confirmation",
                self._device_id,
                sinric_mode,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting thermostat mode, retrying once")
            try:
                await self.coordinator.api.set_thermostat_mode(self._device_id, sinric_mode)
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

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature.

        Args:
            **kwargs: Keyword arguments containing temperature settings.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        # Set pending state
        self._pending_command = True
        self._pending_target_temperature = temperature
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
            await self.coordinator.api.set_target_temperature(self._device_id, temperature)
            _LOGGER.debug(
                "Target temperature command sent for %s to %.1f, waiting for SSE confirmation",
                self._device_id,
                temperature,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting target temperature, retrying once")
            try:
                await self.coordinator.api.set_target_temperature(self._device_id, temperature)
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

    async def async_turn_on(self) -> None:
        """Turn the thermostat on (set to last mode or AUTO).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        # Turn on means setting to a non-OFF mode
        # We'll default to AUTO mode
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        """Turn the thermostat off.

        Raises:
            HomeAssistantError: If the operation fails.
        """
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode (AC units only).

        Args:
            fan_mode: Fan mode to set (FAN_LOW, FAN_MEDIUM, FAN_HIGH).

        Raises:
            HomeAssistantError: If the operation fails.
        """
        if not self._is_ac_unit:
            raise HomeAssistantError("Fan mode control is only available for AC units")

        if fan_mode not in HA_TO_SINRIC_FAN_MODE:
            raise HomeAssistantError(f"Unsupported fan mode: {fan_mode}")

        range_value = HA_TO_SINRIC_FAN_MODE[fan_mode]

        # Set pending state
        self._pending_command = True
        self._pending_fan_mode = fan_mode
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
            await self.coordinator.api.set_range_value(self._device_id, range_value)
            _LOGGER.debug(
                "Fan mode command sent for %s to %s, waiting for SSE confirmation",
                self._device_id,
                fan_mode,
            )

        except SinricProDeviceOfflineError as err:
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Device {self.name} is offline and cannot be controlled"
            ) from err

        except SinricProTimeoutError as err:
            _LOGGER.debug("Timeout setting fan mode, retrying once")
            try:
                await self.coordinator.api.set_range_value(self._device_id, range_value)
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
