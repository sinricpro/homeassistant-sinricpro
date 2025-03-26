"""SinricPro API client."""
import asyncio
import json
import logging
from typing import Any, Dict, Optional, Callable, List
from datetime import datetime, timedelta

import aiohttp
import async_timeout

from .const import API_ENDPOINT, SSE_ENDPOINT

_LOGGER = logging.getLogger(__name__)

class SinricProAPIClient:
    """SinricPro API client."""

    def __init__(
        self, 
        api_key: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        self._api_key = api_key
        self._session = session
        self._access_token = None
        self._refresh_token = None
        self._token_expires = None
        self._devices = {}
        self._sse_task = None
        self._sse_closing = False
        self._callbacks = {}  # Device ID -> list of callbacks

    async def authenticate(self) -> bool:
        """Authenticate with SinricPro API and get access token."""
        try:
            # Check if current token is still valid
            if (self._access_token and self._token_expires and 
                datetime.now() < self._token_expires - timedelta(minutes=10)):
                return True
                
            # If we have a refresh token and it's close to expiry, use refresh flow
            if self._refresh_token and self._token_expires and datetime.now() > self._token_expires - timedelta(minutes=10):
                return await self._refresh_auth()
                
            # Otherwise do a full authentication
            _LOGGER.debug("Authenticating with SinricPro API")
            url = f"{API_ENDPOINT}/api/v1/auth"
            headers = {
                "x-sinric-api-key": self._api_key,
                "Content-Type": "application/json"
            }
            
            async with async_timeout.timeout(10):
                response = await self._session.post(url, headers=headers)
                response.raise_for_status()
                
                data = await response.json()
                
                if not data.get("success"):
                    _LOGGER.error("Authentication failed: %s", data.get("message"))
                    return False
                    
                self._access_token = data.get("accessToken")
                self._refresh_token = data.get("refreshToken")
                
                # Set token expiry (subtract 1 minute for safety)
                expires_in = data.get("expiresIn", 86400)  # Default to 24 hours
                self._token_expires = datetime.now() + timedelta(seconds=expires_in)
                
                _LOGGER.debug("Successfully authenticated with SinricPro API")
                return True
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            _LOGGER.error("Error authenticating with SinricPro API: %s", error)
            return False
            
    async def _refresh_auth(self) -> bool:
        """Refresh authentication token."""
        try:
            _LOGGER.debug("Refreshing SinricPro API token")
            # Implement token refresh logic when SinricPro provides this endpoint
            # For now, just do a full authentication
            
            # Reset tokens and do a full auth
            self._access_token = None
            self._refresh_token = None
            self._token_expires = None
            return await self.authenticate()
            
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            _LOGGER.error("Error refreshing SinricPro API token: %s", error)
            return False
            
    async def get_devices(self) -> Dict[str, Any]:
        """Get all devices from SinricPro."""
        try:
            if not await self.authenticate():
                return {}
                
            url = f"{API_ENDPOINT}/api/v1/devices"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json"
            }
            
            async with async_timeout.timeout(10):
                response = await self._session.get(url, headers=headers)
                response.raise_for_status()
                
                data = await response.json()
                devices = data.get("data", {})
                
                # Process devices and organize by type
                organized_devices = {}
                for device_id, device_data in devices.items():
                    device_type = device_data.get("type", "unknown").lower()
                    if device_type not in organized_devices:
                        organized_devices[device_type] = {}
                    organized_devices[device_type][device_id] = device_data
                
                self._devices = organized_devices
                return self._devices
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            _LOGGER.error("Error getting devices from SinricPro: %s", error)
            return {}
            
    async def get_device_state(self, device_id: str) -> Dict[str, Any]:
        """Get the current state of a device."""
        try:
            if not await self.authenticate():
                return {}
                
            url = f"{API_ENDPOINT}/api/v1/devices/{device_id}/state"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json"
            }
            
            async with async_timeout.timeout(10):
                response = await self._session.get(url, headers=headers)
                response.raise_for_status()
                
                data = await response.json()
                return data.get("data", {})
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            _LOGGER.error("Error getting device state from SinricPro: %s", error)
            return {}
            
    async def set_device_state(self, device_id: str, state: Dict[str, Any]) -> bool:
        """Set the state of a device."""
        try:
            if not await self.authenticate():
                return False
            
            # Determine the appropriate action based on the state values
            action = None
            value = None
            
            if "powerState" in state:
                action = "setPowerState"
                value = json.dumps({"state": state["powerState"]})
            elif "thermostatMode" in state:
                action = "setThermostatMode"
                value = json.dumps({"thermostatMode": state["thermostatMode"]})
            elif "targetTemperature" in state:
                action = "targetTemperature"
                value = json.dumps({"temperature": state["targetTemperature"]})
            else:
                # Default handling for other state types
                # Pass first key as action and the rest as value
                if state:
                    first_key = next(iter(state))
                    action = first_key
                    value = json.dumps({k: v for k, v in state.items() if k != first_key})
            
            if not action or not value:
                _LOGGER.error("Cannot determine action for state: %s", state)
                return False
                
            url = f"{API_ENDPOINT}/api/v1/devices/{device_id}/action"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "type": "request",
                "action": action,
                "value": value
            }
            
            _LOGGER.debug("Sending action to device %s: %s", device_id, payload)
            
            async with async_timeout.timeout(10):
                response = await self._session.post(url, headers=headers, json=payload)
                response.raise_for_status()
                
                data = await response.json()
                success = data.get("success", False)
                
                if not success:
                    _LOGGER.error("Failed to set device state: %s", data.get("message", "Unknown error"))
                    
                return success
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            _LOGGER.error("Error setting device state in SinricPro: %s", error)
            return False
            
    async def start_event_listener(self) -> bool:
        """Start listening for SSE events from SinricPro."""
        if not await self.authenticate():
            _LOGGER.error("Failed to authenticate with SinricPro")
            return False
            
        if self._sse_task is not None:
            # Already listening
            return True
            
        # Start background task to process events
        self._sse_task = asyncio.create_task(self._listen_for_events())
        return True
        
    async def stop_event_listener(self) -> None:
        """Stop listening for SSE events."""
        self._sse_closing = True
        if self._sse_task is not None:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
            self._sse_task = None
        self._sse_closing = False
        
    async def _listen_for_events(self) -> None:
        """Listen for SSE events from SinricPro."""
        while not self._sse_closing:
            if not self._access_token:
                if not await self.authenticate():
                    await asyncio.sleep(10)  # Wait before retrying
                    continue
                    
            try:
                url = f"{SSE_ENDPOINT}?accessToken={self._access_token}"
                headers = {
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache"
                }
                
                _LOGGER.info("Connecting to SinricPro SSE endpoint")
                async with self._session.get(url, headers=headers, timeout=0) as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientError(f"SSE connection failed with status {resp.status}")
                        
                    # Process the SSE stream
                    async for line in resp.content:
                        if self._sse_closing:
                            break
                            
                        line = line.decode('utf-8').strip()
                        if not line:
                            continue
                            
                        if line.startswith('data:'):
                            await self._process_sse_message(line[5:])
                            
            except asyncio.CancelledError:
                break
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                _LOGGER.error("Error in SSE connection: %s", error)
                await asyncio.sleep(5)  # Wait before reconnecting
            except Exception as ex:
                _LOGGER.exception("Unexpected error in SSE listener: %s", ex)
                await asyncio.sleep(5)  # Wait before reconnecting
                
    async def _process_sse_message(self, data: str) -> None:
        """Process a message from the SSE stream."""
        try:
            message = json.loads(data)
            event_type = message.get("event")
            device_data = message.get("device", {})
            device_id = device_data.get("id")
            
            _LOGGER.debug("SSE event received: %s for device %s", event_type, device_id)
            
            if not device_id or device_id not in self._callbacks:
                return
                
            if event_type == "deviceMessageArrived":
                # Device state change event - pass the device data to callbacks
                for callback in self._callbacks[device_id]:
                    try:
                        await callback(device_data)
                    except Exception as ex:
                        _LOGGER.error("Error in callback for device %s: %s", device_id, ex)
                            
            elif event_type in ["deviceConnected", "deviceDisconnected"]:
                # Device connection status change
                available = event_type == "deviceConnected"
                for callback in self._callbacks[device_id]:
                    try:
                        await callback({"id": device_id, "available": available})
                    except Exception as ex:
                        _LOGGER.error("Error in callback for device %s: %s", device_id, ex)
                            
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON in SSE message: %s", data)
        except Exception as ex:
            _LOGGER.exception("Error processing SSE message: %s", ex)
            
    def register_callback(self, device_id: str, callback: Callable) -> None:
        """Register a callback for device events."""
        if device_id not in self._callbacks:
            self._callbacks[device_id] = []
        self._callbacks[device_id].append(callback)
        
    def unregister_callback(self, device_id: str, callback: Callable = None) -> None:
        """Unregister a callback for device events."""
        if device_id in self._callbacks:
            if callback is None:
                # Remove all callbacks for this device
                self._callbacks.pop(device_id)
            elif callback in self._callbacks[device_id]:
                # Remove specific callback
                self._callbacks[device_id].remove(callback)
                if not self._callbacks[device_id]:
                    # No more callbacks for this device
                    self._callbacks.pop(device_id)