"""SSE client for SinricPro real-time updates."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING
from typing import Any

import aiohttp

from .const import HEADER_API_KEY
from .const import SSE_BACKOFF_MULTIPLIER
from .const import SSE_INITIAL_BACKOFF
from .const import SSE_MAX_BACKOFF
from .const import SSE_MAX_RECONNECTION_ATTEMPTS
from .const import SSE_URL
from .exceptions import SinricProAuthenticationError

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)


class SinricProSSE:
    """SSE client for real-time SinricPro updates."""

    def __init__(
        self,
        api_key: str,
        session: ClientSession,
        callback: Callable[[str, str, dict[str, Any]], None],
    ) -> None:
        """Initialize the SSE client.

        Args:
            api_key: SinricPro API key.
            session: aiohttp client session.
            callback: Callback function for events (event_name, device_id, data).
        """
        self._api_key = api_key
        self._session = session
        self._callback = callback
        self._connected = False
        self._should_reconnect = True
        self._reconnection_attempts = 0
        self._current_backoff = SSE_INITIAL_BACKOFF
        self._response: aiohttp.ClientResponse | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        """Return True if connected to SSE stream."""
        return self._connected

    async def connect(self) -> None:
        """Connect to the SSE stream.

        This method starts the SSE connection in a background task.
        """
        if self._task is not None and not self._task.done():
            _LOGGER.debug("SSE connection already active")
            return

        self._should_reconnect = True
        self._reconnection_attempts = 0
        self._current_backoff = SSE_INITIAL_BACKOFF
        self._task = asyncio.create_task(self._run())
        _LOGGER.info("SSE connection task started")

    async def disconnect(self) -> None:
        """Disconnect from the SSE stream."""
        _LOGGER.info("Disconnecting from SSE stream")
        self._should_reconnect = False
        self._connected = False

        if self._response is not None:
            self._response.close()
            self._response = None

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        _LOGGER.debug("SSE disconnected")

    async def _run(self) -> None:
        """Run the SSE connection loop with automatic reconnection."""
        while self._should_reconnect:
            try:
                await self._connect_and_listen()
            except SinricProAuthenticationError:
                _LOGGER.error("SSE authentication failed, stopping reconnection")
                self._should_reconnect = False
                self._connected = False
                break
            except asyncio.CancelledError:
                _LOGGER.debug("SSE task cancelled")
                break
            except Exception:
                _LOGGER.exception("Unexpected error in SSE connection")

            if not self._should_reconnect:
                break

            self._connected = False
            self._reconnection_attempts += 1

            if self._reconnection_attempts >= SSE_MAX_RECONNECTION_ATTEMPTS:
                _LOGGER.error(
                    "Maximum SSE reconnection attempts (%d) reached",
                    SSE_MAX_RECONNECTION_ATTEMPTS,
                )
                break

            _LOGGER.info(
                "SSE reconnecting in %d seconds (attempt %d/%d)",
                self._current_backoff,
                self._reconnection_attempts,
                SSE_MAX_RECONNECTION_ATTEMPTS,
            )
            await asyncio.sleep(self._current_backoff)
            self._current_backoff = min(
                self._current_backoff * SSE_BACKOFF_MULTIPLIER,
                SSE_MAX_BACKOFF,
            )

    async def _connect_and_listen(self) -> None:
        """Establish SSE connection and listen for events."""
        headers = {
            HEADER_API_KEY: self._api_key,
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }

        _LOGGER.debug("Connecting to SSE stream at %s", SSE_URL)

        try:
            self._response = await self._session.get(
                SSE_URL,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=None, sock_read=None),
            )

            if self._response.status in (401, 403):
                raise SinricProAuthenticationError("Invalid API key for SSE")

            if self._response.status != 200:
                _LOGGER.error(
                    "SSE connection failed with status %d",
                    self._response.status,
                )
                return

            self._connected = True
            self._reconnection_attempts = 0
            self._current_backoff = SSE_INITIAL_BACKOFF
            _LOGGER.info("SSE connected successfully")

            await self._process_stream()

        except aiohttp.ClientConnectionError as err:
            _LOGGER.warning("SSE connection error: %s", err)
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise SinricProAuthenticationError("Invalid API key for SSE") from err
            _LOGGER.warning("SSE response error: %s", err)
        finally:
            if self._response is not None:
                self._response.close()
                self._response = None

    async def _process_stream(self) -> None:
        """Process the SSE stream and parse events."""
        if self._response is None:
            return

        event_data = ""
        event_type = ""

        async for line in self._response.content:
            if not self._should_reconnect:
                break

            try:
                decoded_line = line.decode("utf-8").strip()
            except UnicodeDecodeError:
                _LOGGER.warning("Failed to decode SSE line")
                continue

            if not decoded_line:
                # Empty line indicates end of event
                if event_data:
                    self._handle_event(event_type, event_data)
                event_data = ""
                event_type = ""
                continue

            if decoded_line.startswith("event:"):
                event_type = decoded_line[6:].strip()
            elif decoded_line.startswith("data:"):
                event_data = decoded_line[5:].strip()
            elif decoded_line.startswith(":"):
                # Comment line (often used for keep-alive)
                continue

    def _handle_event(self, event_type: str, event_data: str) -> None:
        """Handle an SSE event.

        Args:
            event_type: Type of the event.
            event_data: JSON data of the event.
        """
        try:
            data = json.loads(event_data)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse SSE event data: %s", event_data)
            return

        # Get event name from data
        event_name = data.get("event", "")

        # Ignore heartbeat events
        if event_name == "heartbeat":
            return

        # Handle user alerts (these don't have a specific device context)
        if event_name == "eventUserAlert":
            _LOGGER.debug("SSE user alert received: %s", data)
            try:
                # Pass with empty device_id to indicate this is a user alert
                self._callback(event_name, "", data)
            except Exception:
                _LOGGER.exception("Error in SSE callback for user alert")
            return

        # Extract device_id based on event type
        device_id = self._extract_device_id(event_name, data)
        if not device_id:
            _LOGGER.debug("SSE event without device_id: %s", data)
            return

        _LOGGER.debug(
            "SSE event received - event: %s, device: %s, data: %s",
            event_name,
            device_id,
            data,
        )

        try:
            self._callback(event_name, device_id, data)
        except Exception:
            _LOGGER.exception("Error in SSE callback for device %s", device_id)

    def _extract_device_id(self, event_name: str, data: dict[str, Any]) -> str | None:
        """Extract device ID from event data based on event type.

        Args:
            event_name: Name of the event.
            data: Event data.

        Returns:
            Device ID or None if not found.
        """
        if event_name in ("deviceConnected", "deviceDisconnected"):
            # Device ID is in data['device']['id']
            device = data.get("device", {})
            return device.get("id")

        if event_name == "deviceMessageArrived":
            # Device ID is in data['message']['deviceId']
            message = data.get("message", {})
            return message.get("deviceId")

        # Fallback to top-level deviceId
        return data.get("deviceId") or data.get("device_id")
