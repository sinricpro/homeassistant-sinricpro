"""The SinricPro integration."""
import asyncio
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS, CONF_API_KEY

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the SinricPro component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up SinricPro from a config entry."""
    from .api import SinricProAPIClient
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    
    hass.data.setdefault(DOMAIN, {})
    
    api_key = entry.data[CONF_API_KEY]
    session = async_get_clientsession(hass)
    
    client = SinricProAPIClient(api_key, session)
    
    # Authenticate with SinricPro
    try:
        if not await client.authenticate():
            raise ConfigEntryNotReady("Failed to authenticate with SinricPro API")
    except Exception as ex:
        _LOGGER.error("Error authenticating with SinricPro: %s", ex)
        raise ConfigEntryNotReady(f"Authentication error: {ex}")
    
    # Store client in hass.data
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "config": entry.data,
    }
    
    # Get devices from SinricPro
    try:
        devices = await client.get_devices()
        if not devices:
            _LOGGER.warning("No devices found on SinricPro account")
    except Exception as ex:
        _LOGGER.error("Error getting devices from SinricPro: %s", ex)
    
    # Start SSE event listener for real-time updates
    try:
        if not await client.start_event_listener():
            _LOGGER.warning("Failed to start SinricPro event listener. Real-time updates may not work.")
    except Exception as ex:
        _LOGGER.error("Error starting event listener: %s", ex)
    
    # Setup platform components
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )
    
    # Register service to refresh devices
    async def refresh_devices(call):
        """Refresh devices from SinricPro."""
        client = hass.data[DOMAIN][entry.entry_id]["client"]
        await client.get_devices()
        # Reload platform entities
        for platform in PLATFORMS:
            await hass.config_entries.async_forward_entry_unload(entry, platform)
            await hass.config_entries.async_forward_entry_setup(entry, platform)
    
    # Register service to set device state
    async def set_device_state(call):
        """Set device state in SinricPro."""
        client = hass.data[DOMAIN][entry.entry_id]["client"]
        device_id = call.data.get("device_id")
        state = call.data.get("state", {})
        
        if not device_id:
            _LOGGER.error("Missing required 'device_id' parameter in service call")
            return
            
        await client.set_device_state(device_id, state)
    
    hass.services.async_register(DOMAIN, "refresh_devices", refresh_devices)
    hass.services.async_register(DOMAIN, "set_device_state", set_device_state)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    
    if unload_ok:
        # Stop SSE event listener
        client = hass.data[DOMAIN][entry.entry_id]["client"]
        await client.stop_event_listener()
        
        # Remove from hass.data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok