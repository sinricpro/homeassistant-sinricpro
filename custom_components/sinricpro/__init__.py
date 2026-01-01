"""The SinricPro integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.const import Platform
from homeassistant.core import Event
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinricProApi
from .const import DOMAIN
from .coordinator import SinricProDataUpdateCoordinator
from .exceptions import SinricProAuthenticationError
from .exceptions import SinricProConnectionError
from .exceptions import SinricProTimeoutError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.COVER,
    Platform.EVENT,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.FAN,
    Platform.LOCK,
    Platform.MEDIA_PLAYER,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SinricPro from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.

    Returns:
        True if setup was successful.

    Raises:
        ConfigEntryNotReady: If the integration cannot connect.
    """
    api_key = entry.data[CONF_API_KEY]
    session = async_get_clientsession(hass)

    api = SinricProApi(api_key, session)

    # Validate connection on startup
    try:
        await api.validate_api_key()
    except SinricProAuthenticationError as err:
        _LOGGER.error("Invalid SinricPro API key")
        raise ConfigEntryNotReady("Invalid API key") from err
    except (SinricProConnectionError, SinricProTimeoutError) as err:
        _LOGGER.error("Failed to connect to SinricPro: %s", err)
        raise ConfigEntryNotReady(f"Cannot connect: {err}") from err
    except Exception as err:
        _LOGGER.exception("Unexpected error during SinricPro setup")
        raise ConfigEntryNotReady(f"Unexpected error: {err}") from err

    # Create coordinator
    coordinator = SinricProDataUpdateCoordinator(
        hass,
        api,
        session,
        api_key,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Setup SSE connection
    await coordinator.async_setup()

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register shutdown handler
    async def _async_shutdown(event: Event) -> None:
        """Handle Home Assistant shutdown."""
        _LOGGER.debug("Shutting down SinricPro coordinator")
        await coordinator.async_shutdown()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_shutdown))

    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.

    Returns:
        True if unload was successful.
    """
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Shutdown coordinator
        coordinator: SinricProDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_shutdown()

        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
    """
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
