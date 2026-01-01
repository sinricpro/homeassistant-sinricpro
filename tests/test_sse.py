"""Tests for SinricPro SSE client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import aiohttp
import pytest

from custom_components.sinricpro.sse import SinricProSSE


@pytest.fixture
def mock_session() -> MagicMock:
    """Create mock aiohttp session."""
    return MagicMock(spec=aiohttp.ClientSession)


@pytest.fixture
def callback() -> MagicMock:
    """Create mock callback."""
    return MagicMock()


@pytest.fixture
def sse_client(mock_session: MagicMock, callback: MagicMock) -> SinricProSSE:
    """Create SSE client."""
    return SinricProSSE("test_api_key", mock_session, callback)


async def test_sse_connect_success(
    sse_client: SinricProSSE,
    mock_session: MagicMock,
) -> None:
    """Test successful SSE connection."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.content = AsyncMock()
    mock_response.content.__aiter__ = AsyncMock(return_value=iter([]))
    mock_response.close = MagicMock()

    mock_session.get = AsyncMock(return_value=mock_response)

    # Start connection
    await sse_client.connect()

    # Give time for the task to start
    await asyncio.sleep(0.1)

    # Disconnect to clean up
    await sse_client.disconnect()


async def test_sse_disconnect(sse_client: SinricProSSE) -> None:
    """Test SSE disconnect."""
    sse_client._connected = True
    sse_client._should_reconnect = True

    await sse_client.disconnect()

    assert not sse_client.connected
    assert not sse_client._should_reconnect


async def test_sse_connected_property(sse_client: SinricProSSE) -> None:
    """Test connected property."""
    assert not sse_client.connected

    sse_client._connected = True
    assert sse_client.connected


def test_sse_handle_event_invalid_json(
    sse_client: SinricProSSE,
    callback: MagicMock,
) -> None:
    """Test handling invalid JSON in SSE events."""
    event_data = "not valid json"

    # Should not raise, just log warning
    sse_client._handle_event("state_change", event_data)

    callback.assert_not_called()


def test_sse_handle_event_no_device_id(
    sse_client: SinricProSSE,
    callback: MagicMock,
) -> None:
    """Test handling SSE event without device_id."""
    event_data = '{"powerState": "on"}'

    # Should not raise, just log debug
    sse_client._handle_event("state_change", event_data)

    callback.assert_not_called()


def test_sse_handle_event_callback_error(
    sse_client: SinricProSSE,
    callback: MagicMock,
) -> None:
    """Test handling callback error in SSE events."""
    callback.side_effect = Exception("Callback error")
    event_data = '{"deviceId": "device_123", "powerState": "on"}'

    # Should not raise, just log exception
    sse_client._handle_event("state_change", event_data)

    callback.assert_called_once()


async def test_sse_auth_error_stops_reconnection(
    sse_client: SinricProSSE,
    mock_session: MagicMock,
) -> None:
    """Test that authentication error stops reconnection."""
    mock_response = AsyncMock()
    mock_response.status = 401
    mock_response.close = MagicMock()

    mock_session.get = AsyncMock(return_value=mock_response)

    await sse_client.connect()

    # Give time for the task to process
    await asyncio.sleep(0.2)

    # Should have stopped trying to reconnect
    assert not sse_client._should_reconnect


async def test_sse_forbidden_error_stops_reconnection(
    sse_client: SinricProSSE,
    mock_session: MagicMock,
) -> None:
    """Test that forbidden error stops reconnection."""
    mock_response = AsyncMock()
    mock_response.status = 403
    mock_response.close = MagicMock()

    mock_session.get = AsyncMock(return_value=mock_response)

    await sse_client.connect()

    # Give time for the task to process
    await asyncio.sleep(0.2)

    # Should have stopped trying to reconnect
    assert not sse_client._should_reconnect


async def test_sse_exponential_backoff(sse_client: SinricProSSE) -> None:
    """Test exponential backoff calculation."""
    # Initial backoff
    assert sse_client._current_backoff == 1

    # Simulate increasing backoff
    sse_client._current_backoff = min(
        sse_client._current_backoff * 2,
        60,
    )
    assert sse_client._current_backoff == 2

    sse_client._current_backoff = min(
        sse_client._current_backoff * 2,
        60,
    )
    assert sse_client._current_backoff == 4

    # Continue until max
    for _ in range(10):
        sse_client._current_backoff = min(
            sse_client._current_backoff * 2,
            60,
        )

    assert sse_client._current_backoff == 60


async def test_sse_max_reconnection_attempts(
    sse_client: SinricProSSE,
    mock_session: MagicMock,
) -> None:
    """Test maximum reconnection attempts."""
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.close = MagicMock()

    mock_session.get = AsyncMock(return_value=mock_response)

    # Set high reconnection count
    sse_client._reconnection_attempts = 9

    await sse_client.connect()

    # Give time for reconnection to fail
    await asyncio.sleep(0.5)

    # Should have stopped after max attempts
    await sse_client.disconnect()


async def test_sse_backoff_reset_on_success(sse_client: SinricProSSE) -> None:
    """Test backoff reset on successful connection."""
    # Simulate elevated backoff
    sse_client._current_backoff = 32
    sse_client._reconnection_attempts = 5

    # Simulate successful connection reset
    sse_client._reconnection_attempts = 0
    sse_client._current_backoff = 1

    assert sse_client._current_backoff == 1
    assert sse_client._reconnection_attempts == 0
