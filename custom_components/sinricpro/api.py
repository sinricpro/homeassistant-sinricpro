"""SinricPro API client."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

import aiohttp

from .const import (
    ACTION_DOORBELL_PRESS,
    ACTION_MEDIA_CONTROL,
    ACTION_SET_BRIGHTNESS,
    ACTION_SET_COLOR,
    ACTION_SET_COLOR_TEMPERATURE,
    ACTION_SET_LOCK_STATE,
    ACTION_SET_MODE,
    ACTION_SET_MUTE,
    ACTION_SET_POWER_LEVEL,
    ACTION_SET_POWER_STATE,
    ACTION_SET_RANGE_VALUE,
    ACTION_SET_THERMOSTAT_MODE,
    ACTION_SET_VOLUME,
    ACTION_SKIP_CHANNELS,
    ACTION_TARGET_TEMPERATURE,
    ACTION_TYPE_EVENT,
    ACTION_TYPE_REQUEST,
    API_ACTION_ENDPOINT,
    API_BASE_URL,
    API_DEVICES_ENDPOINT,
    API_MAX_RETRIES,
    API_RETRY_BACKOFF,
    CLIENT_ID,
    DEFAULT_TIMEOUT,
    HEADER_API_KEY,
    POWER_STATE_OFF,
    POWER_STATE_ON,
)
from .exceptions import (
    SinricProApiError,
    SinricProAuthenticationError,
    SinricProConnectionError,
    SinricProDeviceNotFoundError,
    SinricProRateLimitError,
    SinricProTimeoutError,
)

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)


@dataclass
class Device:
    """Representation of a SinricPro device."""

    id: str
    name: str
    device_type: str
    raw_data: dict[str, Any]
    power_state: bool = False
    is_online: bool = True
    brightness: int | None = None
    color: tuple[int, int, int] | None = None  # RGB tuple (r, g, b)
    color_temperature: int | None = None  # Color temperature in Kelvin
    range_value: int | None = None  # Range value for blinds (0-100) or fan speed (1-max)
    last_doorbell_ring: str | None = None  # ISO timestamp of last doorbell ring
    max_fan_speed: int | None = None  # Maximum fan speed levels
    garage_door_state: str | None = None  # Garage door state ("Open" or "Close")
    lock_state: str | None = None  # Lock state ("LOCKED" or "UNLOCKED")
    volume: int | None = None  # Speaker volume (0-100)
    is_muted: bool | None = None  # Speaker mute state
    power_level: int | None = None  # Dimmable switch power level (0-100)
    target_temperature: float | None = None  # Thermostat target temperature
    thermostat_mode: str | None = None  # Thermostat mode (COOL/HEAT/AUTO/OFF)
    temperature: float | None = None  # Current temperature from thermostat sensor
    humidity: float | None = None  # Current humidity from thermostat sensor
    pm1: float | None = None  # Air quality PM1.0
    pm2_5: float | None = None  # Air quality PM2.5
    pm10: float | None = None  # Air quality PM10
    contact_state: str | None = None  # Contact sensor state ("open" or "closed")
    last_contact_detection: str | None = None  # Contact sensor last detection timestamp
    last_motion_state: str | None = None  # Motion sensor state ("detected" or "notDetected")
    last_motion_detection: str | None = None  # Motion sensor last detection timestamp

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Device:
        """Create a Device from API response data.

        Args:
            data: Device data from API response.

        Returns:
            Device instance.
        """
        power_state_str = data.get("powerState", "off")
        power_state = power_state_str.lower() == "on"
        # Handle both API response formats: product.code or deviceType
        if "product" in data:
            device_type = data["product"]["code"]
        else:
            device_type = data.get("deviceType", "unknown")
        is_online = data.get("isOnline", False)
        # Brightness defaults to 100 for lights, None for other devices
        brightness = data.get("brightness", 100)
        # Color defaults to white (255, 255, 255) for lights
        color_data = data.get("color")
        color = None
        if color_data:
            color = (color_data.get("r", 255), color_data.get("g", 255), color_data.get("b", 255))
        else:
            color = (255, 255, 255)  # Default to white
        # Color temperature defaults to 2700K (warm white)
        color_temperature = data.get("colorTemperature", 2700)
        # Range value for blinds (0-100) or fan speed (1-max), defaults to None
        range_value = data.get("rangeValue")
        # Last doorbell ring timestamp
        last_doorbell_ring = data.get("lastDoorbellRing")
        # Max fan speed from fanConfiguration
        fan_config = data.get("fanConfiguration", {})
        max_fan_speed = fan_config.get("maxFanSpeed")
        # Garage door state
        garage_door_state = data.get("garageDoorState")
        # Lock state
        lock_state = data.get("lockState")
        # Speaker volume (0-100)
        volume = data.get("volume")
        # Speaker mute state
        is_muted = data.get("muted")
        # Dimmable switch power level (0-100)
        power_level = data.get("powerLevel")
        # Thermostat target temperature
        target_temperature = data.get("targetTemperature")
        # Thermostat mode
        thermostat_mode = data.get("thermostatMode")
        # Current temperature from thermostat sensor
        temperature = data.get("temperature")
        # Current humidity from thermostat sensor
        humidity = data.get("humidity")
        # Air quality sensor PM values
        air_quality = data.get("airQuality", {})
        pm1 = air_quality.get("pm1")
        pm2_5 = air_quality.get("pm2_5")
        pm10 = air_quality.get("pm10")
        # Contact sensor state
        contact_state = data.get("contactState")
        last_contact_detection = data.get("lastContactDetection")
        # Motion sensor state
        last_motion_state = data.get("lastMotionState")
        last_motion_detection = data.get("lastMotionDetection")

        return cls(
            id=data["id"],
            name=data["name"],
            device_type=device_type,
            power_state=power_state,
            is_online=is_online,
            brightness=brightness,
            color=color,
            color_temperature=color_temperature,
            range_value=range_value,
            last_doorbell_ring=last_doorbell_ring,
            max_fan_speed=max_fan_speed,
            garage_door_state=garage_door_state,
            lock_state=lock_state,
            volume=volume,
            is_muted=is_muted,
            power_level=power_level,
            target_temperature=target_temperature,
            thermostat_mode=thermostat_mode,
            temperature=temperature,
            humidity=humidity,
            pm1=pm1,
            pm2_5=pm2_5,
            pm10=pm10,
            contact_state=contact_state,
            last_contact_detection=last_contact_detection,
            last_motion_state=last_motion_state,
            last_motion_detection=last_motion_detection,
            raw_data=data,
        )


class SinricProApi:
    """SinricPro API client."""

    def __init__(self, api_key: str, session: ClientSession) -> None:
        """Initialize the API client.

        Args:
            api_key: SinricPro API key.
            session: aiohttp client session.
        """
        self._api_key = api_key
        self._session = session
        self._base_url = API_BASE_URL

    @property
    def _headers(self) -> dict[str, str]:
        """Get request headers."""
        return {
            HEADER_API_KEY: self._api_key,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """Make an API request with error handling and retries.

        Args:
            method: HTTP method.
            endpoint: API endpoint.
            json_data: JSON data to send.
            retry_count: Current retry attempt.

        Returns:
            Response data as dictionary.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProRateLimitError: If rate limit is exceeded.
            SinricProDeviceNotFoundError: If device is not found.
            SinricProApiError: For other API errors.
        """
        url = f"{self._base_url}{endpoint}"

        _LOGGER.debug("Request url: %s", url)

        try:
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                async with self._session.request(
                    method,
                    url,
                    headers=self._headers,
                    json=json_data,
                ) as response:
                    return await self._handle_response(
                        response, method, endpoint, json_data, retry_count
                    )

        except asyncio.TimeoutError as err:
            if retry_count < API_MAX_RETRIES:
                _LOGGER.debug(
                    "Request timeout for %s, retrying (%d/%d)",
                    endpoint,
                    retry_count + 1,
                    API_MAX_RETRIES,
                )
                await asyncio.sleep(API_RETRY_BACKOFF * (retry_count + 1))
                return await self._request(method, endpoint, json_data, retry_count + 1)
            raise SinricProTimeoutError(
                f"Request to {endpoint} timed out after {API_MAX_RETRIES} retries"
            ) from err

        except aiohttp.ClientConnectionError as err:
            if retry_count < API_MAX_RETRIES:
                _LOGGER.debug(
                    "Connection error for %s, retrying (%d/%d)",
                    endpoint,
                    retry_count + 1,
                    API_MAX_RETRIES,
                )
                await asyncio.sleep(API_RETRY_BACKOFF * (retry_count + 1))
                return await self._request(method, endpoint, json_data, retry_count + 1)
            raise SinricProConnectionError(
                f"Failed to connect to SinricPro API: {err}"
            ) from err

    async def _handle_response(
        self,
        response: aiohttp.ClientResponse,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None,
        retry_count: int,
    ) -> dict[str, Any]:
        """Handle API response and errors.

        Args:
            response: aiohttp response object.
            method: HTTP method.
            endpoint: API endpoint.
            json_data: JSON data sent.
            retry_count: Current retry attempt.

        Returns:
            Response data as dictionary.

        Raises:
            Various SinricPro exceptions based on response status.
        """
        status = response.status

        if status in (401, 403):
            raise SinricProAuthenticationError(
                "Invalid or expired API key"
            )

        if status == 404:
            raise SinricProDeviceNotFoundError(
                f"Device not found: {endpoint}"
            )

        if status == 429:
            retry_after = response.headers.get("Retry-After")
            retry_after_int = int(retry_after) if retry_after else None
            raise SinricProRateLimitError(
                "Rate limit exceeded",
                retry_after=retry_after_int,
            )

        if status in (408, 504):
            if retry_count < API_MAX_RETRIES:
                _LOGGER.debug(
                    "Timeout status %d for %s, retrying (%d/%d)",
                    status,
                    endpoint,
                    retry_count + 1,
                    API_MAX_RETRIES,
                )
                await asyncio.sleep(API_RETRY_BACKOFF * (retry_count + 1))
                return await self._request(method, endpoint, json_data, retry_count + 1)
            raise SinricProTimeoutError(
                f"Request timed out with status {status}"
            )

        if status in (500, 502, 503):
            if retry_count < API_MAX_RETRIES:
                _LOGGER.debug(
                    "Server error %d for %s, retrying (%d/%d)",
                    status,
                    endpoint,
                    retry_count + 1,
                    API_MAX_RETRIES,
                )
                await asyncio.sleep(API_RETRY_BACKOFF * (retry_count + 1))
                return await self._request(method, endpoint, json_data, retry_count + 1)
            raise SinricProApiError(
                f"Server error: {status}",
                status_code=status,
            )

        if status >= 400:
            raise SinricProApiError(
                f"API error: {status}",
                status_code=status,
            )

        try:
            return await response.json()
        except (aiohttp.ContentTypeError, ValueError) as err:
            _LOGGER.warning("Failed to parse JSON response: %s", err)
            return {}

    async def validate_api_key(self) -> bool:
        """Validate the API key by making a test request.

        Returns:
            True if the API key is valid.

        Raises:
            SinricProAuthenticationError: If the API key is invalid.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
        """
        _LOGGER.debug("Validating API key")
        await self._request("GET", API_DEVICES_ENDPOINT)
        _LOGGER.info("API key validated successfully")
        return True

    async def get_devices(self) -> list[Device]:
        """Get all devices from the SinricPro API.

        Returns:
            List of Device objects.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
        """
        _LOGGER.debug("Fetching devices from SinricPro API")
        response = await self._request("GET", API_DEVICES_ENDPOINT)

        devices_data = response.get("devices", [])
        devices = [Device.from_api_response(d) for d in devices_data]

        _LOGGER.debug("Found %d devices", len(devices))

        for device in devices:
            _LOGGER.debug("\tDevice: %s (%s) type: %s", device.name, device.id, device.device_type)

        return devices

    async def set_power_state(self, device_id: str, state: bool) -> bool:
        """Set the power state of a device.

        Args:
            device_id: The device ID.
            state: True for on, False for off.

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        state_str = POWER_STATE_ON if state else POWER_STATE_OFF
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_POWER_STATE,
            "createdAt": created_at,
            "value": json.dumps({"state": state_str}),
        }

        _LOGGER.debug(
            "Setting power state for device %s to %s (messageId: %s)",
            device_id,
            state_str,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Power state for device %s set to %s",
            device_id,
            state_str,
        )
        return True

    async def set_brightness(self, device_id: str, brightness: int) -> bool:
        """Set the brightness of a light device.

        Args:
            device_id: The device ID.
            brightness: Brightness level (0-100).

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_BRIGHTNESS,
            "createdAt": created_at,
            "value": json.dumps({"brightness": brightness}),
        }

        _LOGGER.debug(
            "Setting brightness for device %s to %d (messageId: %s)",
            device_id,
            brightness,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Brightness for device %s set to %d",
            device_id,
            brightness,
        )
        return True

    async def set_color(
        self, device_id: str, red: int, green: int, blue: int
    ) -> bool:
        """Set the color of a light device.

        Args:
            device_id: The device ID.
            red: Red component (0-255).
            green: Green component (0-255).
            blue: Blue component (0-255).

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_COLOR,
            "createdAt": created_at,
            "value": json.dumps({"color": {"r": red, "g": green, "b": blue}}),
        }

        _LOGGER.debug(
            "Setting color for device %s to RGB(%d, %d, %d) (messageId: %s)",
            device_id,
            red,
            green,
            blue,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Color for device %s set to RGB(%d, %d, %d)",
            device_id,
            red,
            green,
            blue,
        )
        return True

    async def set_color_temperature(self, device_id: str, color_temperature: int) -> bool:
        """Set the color temperature of a light device.

        Args:
            device_id: The device ID.
            color_temperature: Color temperature in Kelvin (1000-10000).

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_COLOR_TEMPERATURE,
            "createdAt": created_at,
            "value": json.dumps({"colorTemperature": color_temperature}),
        }

        _LOGGER.debug(
            "Setting color temperature for device %s to %dK (messageId: %s)",
            device_id,
            color_temperature,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Color temperature for device %s set to %dK",
            device_id,
            color_temperature,
        )
        return True

    async def set_range_value(self, device_id: str, range_value: int) -> bool:
        """Set the range value of a device (used for blinds position).

        Args:
            device_id: The device ID.
            range_value: Range value (0-100). 0 = closed, 100 = open.

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_RANGE_VALUE,
            "createdAt": created_at,
            "value": json.dumps({"rangeValue": range_value}),
        }

        _LOGGER.debug(
            "Setting range value for device %s to %d (messageId: %s)",
            device_id,
            range_value,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Range value for device %s set to %d",
            device_id,
            range_value,
        )
        return True

    async def press_doorbell(self, device_id: str) -> bool:
        """Trigger a doorbell press event.

        Args:
            device_id: The device ID.

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_EVENT,
            "action": ACTION_DOORBELL_PRESS,
            "createdAt": created_at,
            "value": json.dumps({"state": "pressed"}),
        }

        _LOGGER.debug(
            "Pressing doorbell for device %s (messageId: %s)",
            device_id,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Doorbell pressed for device %s",
            device_id,
        )
        return True

    async def set_mode(self, device_id: str, mode: str) -> bool:
        """Set the mode of a device (used for garage door).

        Args:
            device_id: The device ID.
            mode: Mode value ("Open" or "Close").

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_MODE,
            "createdAt": created_at,
            "value": json.dumps({"mode": mode}),
        }

        _LOGGER.debug(
            "Setting mode for device %s to %s (messageId: %s)",
            device_id,
            mode,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Mode for device %s set to %s",
            device_id,
            mode,
        )
        return True

    async def set_lock_state(self, device_id: str, state: str) -> bool:
        """Set the lock state of a device.

        Args:
            device_id: The device ID.
            state: Lock state ("lock" or "unlock").

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_LOCK_STATE,
            "createdAt": created_at,
            "value": json.dumps({"state": state}),
        }

        _LOGGER.debug(
            "Setting lock state for device %s to %s (messageId: %s)",
            device_id,
            state,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Lock state for device %s set to %s",
            device_id,
            state,
        )
        return True

    async def set_volume(self, device_id: str, volume: int) -> bool:
        """Set the volume of a speaker device.

        Args:
            device_id: The device ID.
            volume: Volume level (0-100).

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_VOLUME,
            "createdAt": created_at,
            "value": json.dumps({"volume": volume}),
        }

        _LOGGER.debug(
            "Setting volume for device %s to %d (messageId: %s)",
            device_id,
            volume,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Volume for device %s set to %d",
            device_id,
            volume,
        )
        return True

    async def set_mute(self, device_id: str, muted: bool) -> bool:
        """Set the mute state of a speaker device.

        Args:
            device_id: The device ID.
            muted: True to mute, False to unmute.

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_MUTE,
            "createdAt": created_at,
            "value": json.dumps({"mute": muted}),
        }

        _LOGGER.debug(
            "Setting mute state for device %s to %s (messageId: %s)",
            device_id,
            muted,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Mute state for device %s set to %s",
            device_id,
            muted,
        )
        return True

    async def set_power_level(self, device_id: str, power_level: int) -> bool:
        """Set the power level of a dimmable switch device.

        Args:
            device_id: The device ID.
            power_level: Power level (0-100).

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_POWER_LEVEL,
            "createdAt": created_at,
            "value": json.dumps({"powerLevel": power_level}),
        }

        _LOGGER.debug(
            "Setting power level for device %s to %d (messageId: %s)",
            device_id,
            power_level,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Power level for device %s set to %d",
            device_id,
            power_level,
        )
        return True

    async def skip_channels(self, device_id: str, channel_count: int) -> bool:
        """Skip channels on a TV device.

        Args:
            device_id: The device ID.
            channel_count: Number of channels to skip (positive for up, negative for down).

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SKIP_CHANNELS,
            "createdAt": created_at,
            "value": json.dumps({"channelCount": channel_count}),
        }

        _LOGGER.debug(
            "Skipping channels for device %s by %d (messageId: %s)",
            device_id,
            channel_count,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Channels skipped for device %s by %d",
            device_id,
            channel_count,
        )
        return True

    async def media_control(self, device_id: str, control: str) -> bool:
        """Send media control command to a TV device.

        Args:
            device_id: The device ID.
            control: Media control command ("play", "pause", etc.).

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_MEDIA_CONTROL,
            "createdAt": created_at,
            "value": json.dumps({"control": control}),
        }

        _LOGGER.debug(
            "Sending media control '%s' to device %s (messageId: %s)",
            control,
            device_id,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Media control '%s' sent to device %s",
            control,
            device_id,
        )
        return True

    async def set_target_temperature(
        self, device_id: str, temperature: float
    ) -> bool:
        """Set the target temperature of a thermostat device.

        Args:
            device_id: The device ID.
            temperature: Target temperature in Celsius.

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_TARGET_TEMPERATURE,
            "createdAt": created_at,
            "value": json.dumps({"temperature": temperature}),
        }

        _LOGGER.debug(
            "Setting target temperature for device %s to %.1f (messageId: %s)",
            device_id,
            temperature,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Target temperature for device %s set to %.1f",
            device_id,
            temperature,
        )
        return True

    async def set_thermostat_mode(self, device_id: str, mode: str) -> bool:
        """Set the thermostat mode of a thermostat device.

        Args:
            device_id: The device ID.
            mode: Thermostat mode (COOL, HEAT, AUTO, OFF).

        Returns:
            True if successful.

        Raises:
            SinricProAuthenticationError: If authentication fails.
            SinricProConnectionError: If connection fails.
            SinricProTimeoutError: If request times out.
            SinricProDeviceNotFoundError: If device is not found.
        """
        endpoint = API_ACTION_ENDPOINT.format(device_id=device_id)
        message_id = str(uuid.uuid4())
        created_at = str(int(time.time()))

        payload = {
            "clientId": CLIENT_ID,
            "messageId": message_id,
            "type": ACTION_TYPE_REQUEST,
            "action": ACTION_SET_THERMOSTAT_MODE,
            "createdAt": created_at,
            "value": json.dumps({"thermostatMode": mode}),
        }

        _LOGGER.debug(
            "Setting thermostat mode for device %s to %s (messageId: %s)",
            device_id,
            mode,
            message_id,
        )
        await self._request("POST", endpoint, json_data=payload)
        _LOGGER.info(
            "Thermostat mode for device %s set to %s",
            device_id,
            mode,
        )
        return True
