"""Tests for SinricPro API client."""
from __future__ import annotations

import asyncio

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.sinricpro.api import Device
from custom_components.sinricpro.api import SinricProApi
from custom_components.sinricpro.const import (
    API_BASE_URL,
    API_DEVICES_ENDPOINT,
    DEVICE_TYPE_SWITCH,
)
from custom_components.sinricpro.exceptions import (
    SinricProApiError,
    SinricProAuthenticationError,
    SinricProConnectionError,
    SinricProDeviceNotFoundError,
    SinricProRateLimitError,
    SinricProTimeoutError,
)


@pytest.fixture
def api_url() -> str:
    """Return the API URL."""
    return f"{API_BASE_URL}{API_DEVICES_ENDPOINT}"


@pytest.fixture
async def session() -> aiohttp.ClientSession:
    """Create aiohttp session."""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def api(session: aiohttp.ClientSession) -> SinricProApi:
    """Create API client."""
    return SinricProApi("test_api_key", session)


async def test_api_validate_key_success(
    api: SinricProApi, api_url: str
) -> None:
    """Test successful API key validation."""
    with aioresponses() as m:
        m.get(api_url, payload={"devices": []})

        result = await api.validate_api_key()
        assert result is True


async def test_api_validate_key_invalid(
    api: SinricProApi, api_url: str
) -> None:
    """Test invalid API key validation."""
    with aioresponses() as m:
        m.get(api_url, status=401)

        with pytest.raises(SinricProAuthenticationError):
            await api.validate_api_key()


async def test_api_validate_key_forbidden(
    api: SinricProApi, api_url: str
) -> None:
    """Test forbidden API key validation."""
    with aioresponses() as m:
        m.get(api_url, status=403)

        with pytest.raises(SinricProAuthenticationError):
            await api.validate_api_key()


async def test_api_get_devices(api: SinricProApi, api_url: str) -> None:
    """Test getting devices from API."""
    devices_data = {
        "devices": [
            {
                "id": "device_123",
                "name": "Living Room Light",
                "deviceType": DEVICE_TYPE_SWITCH,
                "powerState": "on",
            },
            {
                "id": "device_456",
                "name": "Kitchen Light",
                "deviceType": DEVICE_TYPE_SWITCH,
                "powerState": "off",
            },
        ]
    }

    with aioresponses() as m:
        m.get(api_url, payload=devices_data)

        devices = await api.get_devices()

        assert len(devices) == 2
        assert devices[0].id == "device_123"
        assert devices[0].name == "Living Room Light"
        assert devices[0].device_type == DEVICE_TYPE_SWITCH
        assert devices[0].power_state is True
        assert devices[1].id == "device_456"
        assert devices[1].power_state is False


async def test_api_get_devices_empty(api: SinricProApi, api_url: str) -> None:
    """Test getting empty device list."""
    with aioresponses() as m:
        m.get(api_url, payload={"devices": []})

        devices = await api.get_devices()
        assert len(devices) == 0


async def test_api_set_power_state_on(api: SinricProApi) -> None:
    """Test setting power state to on."""
    action_url = f"{API_BASE_URL}/api/v1/devices/device_123/action"

    with aioresponses() as m:
        m.post(action_url, payload={"success": True})

        result = await api.set_power_state("device_123", True)
        assert result is True


async def test_api_set_power_state_off(api: SinricProApi) -> None:
    """Test setting power state to off."""
    action_url = f"{API_BASE_URL}/api/v1/devices/device_456/action"

    with aioresponses() as m:
        m.post(action_url, payload={"success": True})

        result = await api.set_power_state("device_456", False)
        assert result is True


async def test_api_device_not_found(api: SinricProApi) -> None:
    """Test device not found error."""
    action_url = f"{API_BASE_URL}/api/v1/devices/unknown_device/action"

    with aioresponses() as m:
        m.post(action_url, status=404)

        with pytest.raises(SinricProDeviceNotFoundError):
            await api.set_power_state("unknown_device", True)


async def test_api_rate_limit(api: SinricProApi, api_url: str) -> None:
    """Test rate limit error."""
    with aioresponses() as m:
        m.get(api_url, status=429, headers={"Retry-After": "60"})

        with pytest.raises(SinricProRateLimitError) as exc_info:
            await api.get_devices()

        assert exc_info.value.retry_after == 60


async def test_api_rate_limit_no_retry_header(
    api: SinricProApi, api_url: str
) -> None:
    """Test rate limit error without Retry-After header."""
    with aioresponses() as m:
        m.get(api_url, status=429)

        with pytest.raises(SinricProRateLimitError) as exc_info:
            await api.get_devices()

        assert exc_info.value.retry_after is None


async def test_api_server_error(api: SinricProApi, api_url: str) -> None:
    """Test server error handling with retries."""
    with aioresponses() as m:
        # Add multiple responses for retry attempts
        m.get(api_url, status=500)
        m.get(api_url, status=500)
        m.get(api_url, status=500)
        m.get(api_url, status=500)

        with pytest.raises(SinricProApiError) as exc_info:
            await api.get_devices()

        assert exc_info.value.status_code == 500


async def test_api_malformed_response(api: SinricProApi, api_url: str) -> None:
    """Test handling of malformed JSON response."""
    with aioresponses() as m:
        m.get(api_url, body="not json", content_type="text/plain")

        # Should return empty dict instead of raising
        devices = await api.get_devices()
        assert devices == []


async def test_api_connection_error(api: SinricProApi, api_url: str) -> None:
    """Test connection error handling."""
    with aioresponses() as m:
        # Simulate connection error for all retries
        m.get(api_url, exception=aiohttp.ClientConnectionError())
        m.get(api_url, exception=aiohttp.ClientConnectionError())
        m.get(api_url, exception=aiohttp.ClientConnectionError())
        m.get(api_url, exception=aiohttp.ClientConnectionError())

        with pytest.raises(SinricProConnectionError):
            await api.get_devices()


async def test_api_timeout(api: SinricProApi, api_url: str) -> None:
    """Test timeout error handling."""
    with aioresponses() as m:
        # Simulate timeout for all retries
        m.get(api_url, exception=asyncio.TimeoutError())
        m.get(api_url, exception=asyncio.TimeoutError())
        m.get(api_url, exception=asyncio.TimeoutError())
        m.get(api_url, exception=asyncio.TimeoutError())

        with pytest.raises(SinricProTimeoutError):
            await api.get_devices()


async def test_api_timeout_status_code(api: SinricProApi, api_url: str) -> None:
    """Test timeout status code (408) handling."""
    with aioresponses() as m:
        m.get(api_url, status=408)
        m.get(api_url, status=408)
        m.get(api_url, status=408)
        m.get(api_url, status=408)

        with pytest.raises(SinricProTimeoutError):
            await api.get_devices()


async def test_api_gateway_timeout(api: SinricProApi, api_url: str) -> None:
    """Test gateway timeout (504) handling."""
    with aioresponses() as m:
        m.get(api_url, status=504)
        m.get(api_url, status=504)
        m.get(api_url, status=504)
        m.get(api_url, status=504)

        with pytest.raises(SinricProTimeoutError):
            await api.get_devices()


async def test_api_retry_success(api: SinricProApi, api_url: str) -> None:
    """Test successful retry after transient error."""
    with aioresponses() as m:
        # First request fails, second succeeds
        m.get(api_url, status=500)
        m.get(api_url, payload={"devices": []})

        devices = await api.get_devices()
        assert devices == []


def test_device_from_api_response() -> None:
    """Test Device creation from API response."""
    data = {
        "id": "device_123",
        "name": "Test Device",
        "deviceType": "switch",
        "powerState": "On",
        "extra": "data",
    }

    device = Device.from_api_response(data)

    assert device.id == "device_123"
    assert device.name == "Test Device"
    assert device.device_type == "switch"
    assert device.power_state is True
    assert device.raw_data == data


def test_device_from_api_response_off() -> None:
    """Test Device creation with off state."""
    data = {
        "id": "device_456",
        "name": "Test Device Off",
        "deviceType": "switch",
        "powerState": "off",
    }

    device = Device.from_api_response(data)

    assert device.power_state is False


def test_device_from_api_response_missing_power_state() -> None:
    """Test Device creation with missing power state."""
    data = {
        "id": "device_789",
        "name": "Test Device",
        "deviceType": "switch",
    }

    device = Device.from_api_response(data)

    assert device.power_state is False


def test_device_from_api_response_missing_device_type() -> None:
    """Test Device creation with missing device type."""
    data = {
        "id": "device_abc",
        "name": "Test Device",
        "powerState": "on",
    }

    device = Device.from_api_response(data)

    assert device.device_type == "unknown"
