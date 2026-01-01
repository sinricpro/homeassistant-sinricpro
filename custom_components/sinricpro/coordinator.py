"""Data update coordinator for SinricPro."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import Device
from .api import SinricProApi
from .const import DEFAULT_SCAN_INTERVAL
from .const import DOMAIN
from .exceptions import SinricProAuthenticationError
from .exceptions import SinricProConnectionError
from .exceptions import SinricProRateLimitError
from .exceptions import SinricProTimeoutError
from .sse import SinricProSSE

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)


class SinricProDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Device]]):
    """Coordinator for SinricPro data updates."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: SinricProApi,
        session: ClientSession,
        api_key: str,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            api: SinricPro API client.
            session: aiohttp client session.
            api_key: SinricPro API key.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self._api_key = api_key
        self._session = session
        self._sse: SinricProSSE | None = None
        self._devices: dict[str, Device] = {}
        self._doorbell_callbacks: dict[str, list[Callable[[str], None]]] = {}

    @property
    def sse_connected(self) -> bool:
        """Return True if SSE is connected."""
        return self._sse is not None and self._sse.connected

    async def async_setup(self) -> None:
        """Set up the coordinator including SSE connection."""
        # Start SSE connection
        self._sse = SinricProSSE(
            self._api_key,
            self._session,
            self._handle_sse_event,
        )
        await self._sse.connect()

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and disconnect SSE."""
        if self._sse is not None:
            await self._sse.disconnect()
            self._sse = None

    async def _async_update_data(self) -> dict[str, Device]:
        """Fetch data from API.

        This is the method called by the DataUpdateCoordinator
        at the configured update interval.

        Returns:
            Dictionary mapping device IDs to Device objects.

        Raises:
            ConfigEntryAuthFailed: If authentication fails.
            UpdateFailed: If the update fails.
        """
        try:
            devices = await self.api.get_devices()

            # Update internal device storage
            self._devices = {device.id: device for device in devices}

            _LOGGER.debug(
                "Updated %d devices from API",
                len(self._devices),
            )
            return self._devices

        except SinricProAuthenticationError as err:
            # Trigger reauthentication flow
            raise ConfigEntryAuthFailed(
                "Invalid API key, reauthentication required"
            ) from err

        except SinricProRateLimitError as err:
            _LOGGER.warning(
                "Rate limit exceeded, retry after %s seconds",
                err.retry_after,
            )
            # Wait for rate limit to clear before failing
            if err.retry_after:
                await asyncio.sleep(err.retry_after)
            raise UpdateFailed(f"Rate limit exceeded: {err}") from err

        except (SinricProConnectionError, SinricProTimeoutError) as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        except Exception as err:
            _LOGGER.exception("Unexpected error fetching SinricPro data")
            raise UpdateFailed(f"Unexpected error: {err}") from err

    @callback
    def _handle_sse_event(
        self, event_name: str, device_id: str, data: dict[str, Any]
    ) -> None:
        """Handle an SSE event.

        Args:
            event_name: Name of the event.
            device_id: The device ID (empty string for user alerts).
            data: Event data.
        """
        # Handle user alerts (device_id is empty string)
        if event_name == "eventUserAlert":
            self._handle_user_alert(data)
            return

        if device_id not in self._devices:
            _LOGGER.debug(
                "Received SSE event '%s' for unknown device: %s",
                event_name,
                device_id,
            )
            return

        device = self._devices[device_id]

        if event_name == "deviceConnected":
            self._handle_device_connected(device_id, device)
        elif event_name == "deviceDisconnected":
            self._handle_device_disconnected(device_id, device)
        elif event_name == "deviceMessageArrived":
            self._handle_device_message(device_id, device, data)

    @callback
    def _handle_device_connected(self, device_id: str, device: Device) -> None:
        """Handle device connected event.

        Args:
            device_id: The device ID.
            device: The device object.
        """
        if device.is_online:
            return  # Already online, no change needed

        _LOGGER.info(
            "SSE update: Device %s (%s) is now online",
            device.name,
            device_id,
        )
        self._devices[device_id] = Device(
            id=device.id,
            name=device.name,
            device_type=device.device_type,
            power_state=device.power_state,
            is_online=True,
            brightness=device.brightness,
            color=device.color,
            color_temperature=device.color_temperature,
            range_value=device.range_value,
            last_doorbell_ring=device.last_doorbell_ring,
            max_fan_speed=device.max_fan_speed,
            garage_door_state=device.garage_door_state,
            lock_state=device.lock_state,
            volume=device.volume,
            is_muted=device.is_muted,
            power_level=device.power_level,
            target_temperature=device.target_temperature,
            thermostat_mode=device.thermostat_mode,
            temperature=device.temperature,
            humidity=device.humidity,
            pm1=device.pm1,
            pm2_5=device.pm2_5,
            pm10=device.pm10,
            contact_state=device.contact_state,
            last_contact_detection=device.last_contact_detection,
            last_motion_state=device.last_motion_state,
            last_motion_detection=device.last_motion_detection,
            raw_data=device.raw_data,
        )
        self.async_set_updated_data(self._devices)

    @callback
    def _handle_device_disconnected(self, device_id: str, device: Device) -> None:
        """Handle device disconnected event.

        Args:
            device_id: The device ID.
            device: The device object.
        """
        if not device.is_online:
            return  # Already offline, no change needed

        _LOGGER.info(
            "SSE update: Device %s (%s) is now offline",
            device.name,
            device_id,
        )
        self._devices[device_id] = Device(
            id=device.id,
            name=device.name,
            device_type=device.device_type,
            power_state=device.power_state,
            is_online=False,
            brightness=device.brightness,
            color=device.color,
            color_temperature=device.color_temperature,
            range_value=device.range_value,
            last_doorbell_ring=device.last_doorbell_ring,
            max_fan_speed=device.max_fan_speed,
            garage_door_state=device.garage_door_state,
            lock_state=device.lock_state,
            volume=device.volume,
            is_muted=device.is_muted,
            power_level=device.power_level,
            target_temperature=device.target_temperature,
            thermostat_mode=device.thermostat_mode,
            temperature=device.temperature,
            humidity=device.humidity,
            pm1=device.pm1,
            pm2_5=device.pm2_5,
            pm10=device.pm10,
            contact_state=device.contact_state,
            last_contact_detection=device.last_contact_detection,
            last_motion_state=device.last_motion_state,
            last_motion_detection=device.last_motion_detection,
            raw_data=device.raw_data,
        )
        self.async_set_updated_data(self._devices)

    @callback
    def _handle_device_message(
        self, device_id: str, device: Device, data: dict[str, Any]
    ) -> None:
        """Handle device message arrived event.

        Args:
            device_id: The device ID.
            device: The device object.
            data: Event data containing message payload.
        """
        message = data.get("message", {})
        payload = message.get("payload", {})
        value = payload.get("value", {})
        action = payload.get("action")

        # Handle doorbell press event
        if action == "DoorbellPress":
            state = value.get("state")
            if state == "pressed":
                timestamp = datetime.now(UTC).isoformat()
                _LOGGER.info(
                    "SSE update: Device %s (%s) doorbell pressed",
                    device.name,
                    device_id,
                )
                # Update last_doorbell_ring
                self._devices[device_id] = Device(
                    id=device.id,
                    name=device.name,
                    device_type=device.device_type,
                    power_state=device.power_state,
                    is_online=device.is_online,
                    brightness=device.brightness,
                    color=device.color,
                    color_temperature=device.color_temperature,
                    range_value=device.range_value,
                    last_doorbell_ring=timestamp,
                    max_fan_speed=device.max_fan_speed,
                    garage_door_state=device.garage_door_state,
                    lock_state=device.lock_state,
                    volume=device.volume,
                    is_muted=device.is_muted,
                    power_level=device.power_level,
                    target_temperature=device.target_temperature,
                    thermostat_mode=device.thermostat_mode,
                    temperature=device.temperature,
                    humidity=device.humidity,
                    pm1=device.pm1,
                    pm2_5=device.pm2_5,
                    pm10=device.pm10,
                    contact_state=device.contact_state,
                    last_contact_detection=device.last_contact_detection,
                    last_motion_state=device.last_motion_state,
                    last_motion_detection=device.last_motion_detection,
                    raw_data=device.raw_data,
                )
                self.async_set_updated_data(self._devices)
                # Fire doorbell event callbacks
                self._fire_doorbell_event(device_id, timestamp)
            return

        # Track if any changes were made
        new_power_state = device.power_state
        new_brightness = device.brightness
        new_color = device.color
        new_color_temperature = device.color_temperature
        new_range_value = device.range_value
        new_last_doorbell_ring = device.last_doorbell_ring
        new_garage_door_state = device.garage_door_state
        new_lock_state = device.lock_state
        new_volume = device.volume
        new_is_muted = device.is_muted
        new_power_level = device.power_level
        new_target_temperature = device.target_temperature
        new_thermostat_mode = device.thermostat_mode
        new_temperature = device.temperature
        new_humidity = device.humidity
        new_pm1 = device.pm1
        new_pm2_5 = device.pm2_5
        new_pm10 = device.pm10
        new_contact_state = device.contact_state
        new_last_contact_detection = device.last_contact_detection
        new_last_motion_state = device.last_motion_state
        new_last_motion_detection = device.last_motion_detection
        changed = False

        # Check for state changes based on action type
        # value.state is used for both power state and lock state
        state_str = value.get("state")
        if state_str is not None:
            if action == "setLockState":
                # Lock state: "LOCKED" or "UNLOCKED"
                new_lock_state = state_str
                if device.lock_state != new_lock_state:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) lock state changed to %s",
                        device.name,
                        device_id,
                        state_str,
                    )
                    changed = True
            elif action == "setPowerState":
                # Power state: "On" or "Off"
                new_power_state = state_str.lower() == "on"
                if device.power_state != new_power_state:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) power state changed to %s",
                        device.name,
                        device_id,
                        state_str,
                    )
                    changed = True

        # Check for brightness change
        brightness = value.get("brightness")
        if brightness is not None:
            new_brightness = brightness
            if device.brightness != new_brightness:
                _LOGGER.info(
                    "SSE update: Device %s (%s) brightness changed to %d",
                    device.name,
                    device_id,
                    brightness,
                )
                changed = True

        # Check for color change
        color_data = value.get("color")
        if color_data is not None:
            new_color = (
                color_data.get("r", 255),
                color_data.get("g", 255),
                color_data.get("b", 255),
            )
            if device.color != new_color:
                _LOGGER.info(
                    "SSE update: Device %s (%s) color changed to RGB(%d, %d, %d)",
                    device.name,
                    device_id,
                    new_color[0],
                    new_color[1],
                    new_color[2],
                )
                changed = True

        # Check for color temperature change
        color_temperature = value.get("colorTemperature")
        if color_temperature is not None:
            new_color_temperature = color_temperature
            if device.color_temperature != new_color_temperature:
                _LOGGER.info(
                    "SSE update: Device %s (%s) color temperature changed to %dK",
                    device.name,
                    device_id,
                    color_temperature,
                )
                changed = True

        # Check for range value change (blinds position)
        range_value = value.get("rangeValue")
        if range_value is not None:
            new_range_value = range_value
            if device.range_value != new_range_value:
                _LOGGER.info(
                    "SSE update: Device %s (%s) range value changed to %d",
                    device.name,
                    device_id,
                    range_value,
                )
                changed = True

        # Check for mode change (garage door)
        mode = value.get("mode")
        if mode is not None:
            new_garage_door_state = mode
            if device.garage_door_state != new_garage_door_state:
                _LOGGER.info(
                    "SSE update: Device %s (%s) mode changed to %s",
                    device.name,
                    device_id,
                    mode,
                )
                changed = True

        # Check for volume change (speaker)
        volume = value.get("volume")
        if volume is not None:
            new_volume = volume
            if device.volume != new_volume:
                _LOGGER.info(
                    "SSE update: Device %s (%s) volume changed to %d",
                    device.name,
                    device_id,
                    volume,
                )
                changed = True

        # Check for mute state change (speaker)
        mute = value.get("mute")
        if mute is not None:
            new_is_muted = mute
            if device.is_muted != new_is_muted:
                _LOGGER.info(
                    "SSE update: Device %s (%s) mute state changed to %s",
                    device.name,
                    device_id,
                    mute,
                )
                changed = True

        # Check for power level change (dimmable switch)
        power_level = value.get("powerLevel")
        if power_level is not None:
            new_power_level = power_level
            if device.power_level != new_power_level:
                _LOGGER.info(
                    "SSE update: Device %s (%s) power level changed to %d",
                    device.name,
                    device_id,
                    power_level,
                )
                changed = True

        # Check for thermostat changes
        # Handle temperature value based on action type
        temperature_value = value.get("temperature")
        if temperature_value is not None:
            if action == "targetTemperature":
                # Target temperature set point
                new_target_temperature = temperature_value
                if device.target_temperature != new_target_temperature:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) target temperature changed to %.1f",
                        device.name,
                        device_id,
                        temperature_value,
                    )
                    changed = True
            elif action == "currentTemperature":
                # Current temperature from sensor
                new_temperature = temperature_value
                if device.temperature != new_temperature:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) current temperature changed to %.1f",
                        device.name,
                        device_id,
                        temperature_value,
                    )
                    changed = True

        # Check for thermostat mode change
        thermostat_mode = value.get("thermostatMode")
        if thermostat_mode is not None:
            new_thermostat_mode = thermostat_mode
            if device.thermostat_mode != new_thermostat_mode:
                _LOGGER.info(
                    "SSE update: Device %s (%s) thermostat mode changed to %s",
                    device.name,
                    device_id,
                    thermostat_mode,
                )
                changed = True

        # Check for humidity change (thermostat sensor)
        humidity = value.get("humidity")
        if humidity is not None:
            new_humidity = humidity
            if device.humidity != new_humidity:
                _LOGGER.info(
                    "SSE update: Device %s (%s) humidity changed to %.1f",
                    device.name,
                    device_id,
                    humidity,
                )
                changed = True

        # Check for air quality changes (air quality sensor)
        if action == "airQuality":
            pm1_value = value.get("pm1")
            pm2_5_value = value.get("pm2_5")
            pm10_value = value.get("pm10")

            if pm1_value is not None:
                new_pm1 = pm1_value
                if device.pm1 != new_pm1:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) PM1.0 changed to %.1f",
                        device.name,
                        device_id,
                        pm1_value,
                    )
                    changed = True

            if pm2_5_value is not None:
                new_pm2_5 = pm2_5_value
                if device.pm2_5 != new_pm2_5:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) PM2.5 changed to %.1f",
                        device.name,
                        device_id,
                        pm2_5_value,
                    )
                    changed = True

            if pm10_value is not None:
                new_pm10 = pm10_value
                if device.pm10 != new_pm10:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) PM10 changed to %.1f",
                        device.name,
                        device_id,
                        pm10_value,
                    )
                    changed = True

        # Check for contact sensor state changes
        if action == "setContactState":
            contact_state_value = value.get("state")
            if contact_state_value is not None:
                new_contact_state = contact_state_value
                if device.contact_state != new_contact_state:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) contact state changed to %s",
                        device.name,
                        device_id,
                        contact_state_value,
                    )
                    changed = True
                    # Update last detection timestamp
                    if contact_state_value == "open":
                        new_last_contact_detection = datetime.now(UTC).isoformat()

        # Check for motion sensor state changes
        if action == "motion":
            motion_state_value = value.get("state")
            if motion_state_value is not None:
                new_last_motion_state = motion_state_value
                if device.last_motion_state != new_last_motion_state:
                    _LOGGER.info(
                        "SSE update: Device %s (%s) motion state changed to %s",
                        device.name,
                        device_id,
                        motion_state_value,
                    )
                    changed = True
                    # Update last detection timestamp
                    new_last_motion_detection = datetime.now(UTC).isoformat()

        if changed:
            self._devices[device_id] = Device(
                id=device.id,
                name=device.name,
                device_type=device.device_type,
                power_state=new_power_state,
                is_online=device.is_online,
                brightness=new_brightness,
                color=new_color,
                color_temperature=new_color_temperature,
                range_value=new_range_value,
                last_doorbell_ring=new_last_doorbell_ring,
                max_fan_speed=device.max_fan_speed,
                garage_door_state=new_garage_door_state,
                lock_state=new_lock_state,
                volume=new_volume,
                is_muted=new_is_muted,
                power_level=new_power_level,
                target_temperature=new_target_temperature,
                thermostat_mode=new_thermostat_mode,
                temperature=new_temperature,
                humidity=new_humidity,
                pm1=new_pm1,
                pm2_5=new_pm2_5,
                pm10=new_pm10,
                contact_state=new_contact_state,
                last_contact_detection=new_last_contact_detection,
                last_motion_state=new_last_motion_state,
                last_motion_detection=new_last_motion_detection,
                raw_data=device.raw_data,
            )
            self.async_set_updated_data(self._devices)

    def update_device_state(self, device_id: str, power_state: bool) -> None:
        """Update device state locally (for optimistic updates).

        Args:
            device_id: The device ID.
            power_state: New power state.
        """
        if device_id not in self._devices:
            return

        device = self._devices[device_id]
        self._devices[device_id] = Device(
            id=device.id,
            name=device.name,
            device_type=device.device_type,
            power_state=power_state,
            is_online=device.is_online,
            brightness=device.brightness,
            color=device.color,
            color_temperature=device.color_temperature,
            range_value=device.range_value,
            last_doorbell_ring=device.last_doorbell_ring,
            max_fan_speed=device.max_fan_speed,
            garage_door_state=device.garage_door_state,
            lock_state=device.lock_state,
            volume=device.volume,
            is_muted=device.is_muted,
            power_level=device.power_level,
            target_temperature=device.target_temperature,
            thermostat_mode=device.thermostat_mode,
            temperature=device.temperature,
            humidity=device.humidity,
            pm1=device.pm1,
            pm2_5=device.pm2_5,
            pm10=device.pm10,
            contact_state=device.contact_state,
            last_contact_detection=device.last_contact_detection,
            last_motion_state=device.last_motion_state,
            last_motion_detection=device.last_motion_detection,
            raw_data=device.raw_data,
        )
        self.async_set_updated_data(self._devices)

    def get_device(self, device_id: str) -> Device | None:
        """Get a device by ID.

        Args:
            device_id: The device ID.

        Returns:
            Device object or None if not found.
        """
        return self._devices.get(device_id)

    def register_doorbell_callback(
        self, device_id: str, callback_func: Callable[[str], None]
    ) -> Callable[[], None]:
        """Register a callback for doorbell press events.

        Args:
            device_id: The device ID to listen for.
            callback_func: Callback function that receives the timestamp.

        Returns:
            A function to unregister the callback.
        """
        if device_id not in self._doorbell_callbacks:
            self._doorbell_callbacks[device_id] = []
        self._doorbell_callbacks[device_id].append(callback_func)

        def unregister() -> None:
            if device_id in self._doorbell_callbacks:
                self._doorbell_callbacks[device_id].remove(callback_func)
                if not self._doorbell_callbacks[device_id]:
                    del self._doorbell_callbacks[device_id]

        return unregister

    def _fire_doorbell_event(self, device_id: str, timestamp: str) -> None:
        """Fire doorbell press event to registered callbacks.

        Args:
            device_id: The device ID.
            timestamp: ISO timestamp of the event.
        """
        if device_id in self._doorbell_callbacks:
            for callback_func in self._doorbell_callbacks[device_id]:
                callback_func(timestamp)

    @callback
    def _handle_user_alert(self, data: dict[str, Any]) -> None:
        """Handle user alert from SinricPro.

        Args:
            data: Alert event data.
        """
        message_data = data.get("message", {})
        alert_message = message_data.get("message", "Unknown alert")
        alert_type = message_data.get("type", "info")
        user_id = message_data.get("userId", "")
        device_id = message_data.get("deviceId", "")

        _LOGGER.info(
            "SinricPro alert received - type: %s, message: %s",
            alert_type,
            alert_message,
        )

        # Get device name if device_id is available
        device_name = None
        if device_id and device_id in self._devices:
            device = self._devices[device_id]
            device_name = device.name

        # Create notification title based on alert type
        if alert_type == "error":
            title = "SinricPro Error"
        elif alert_type == "warning":
            title = "SinricPro Warning"
        else:
            title = "SinricPro Alert"

        # Format the notification message
        notification_message = alert_message
        if device_name:
            notification_message = f"Device: {device_name}\n\n{alert_message}"

        # Create persistent notification
        persistent_notification.async_create(
            self.hass,
            notification_message,
            title=title,
            notification_id=f"sinricpro_alert_{user_id}_{device_id}",
        )

        # Fire Home Assistant event for automations
        self.hass.bus.async_fire(
            "sinricpro_alert",
            {
                "message": alert_message,
                "type": alert_type,
                "user_id": user_id,
                "device_id": device_id,
                "device_name": device_name,
            },
        )
