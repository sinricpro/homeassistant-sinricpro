"""Config flow for SinricPro integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp

from .const import DOMAIN, CONF_API_KEY, API_ENDPOINT

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
    }
)


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    from .api import SinricProAPIClient
    
    api_key = data[CONF_API_KEY]

    try:
        # Check credentials by connecting to SinricPro API
        session = async_get_clientsession(hass)
        client = SinricProAPIClient(api_key, session)
        
        # Try to authenticate
        if not await client.authenticate():
            raise InvalidAuth
            
        # Try to fetch devices to ensure credentials are valid
        devices = await client.get_devices()
        if not devices:
            _LOGGER.warning("No devices found with the provided API key")
        
    except aiohttp.ClientError:
        raise CannotConnect
    except Exception as ex:
        _LOGGER.error(f"Error validating credentials: {ex}")
        raise InvalidAuth
    
    # Return info to be stored in the config entry
    return {"title": "SinricPro"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SinricPro."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                
                return self.async_create_entry(
                    title=info["title"], data=user_input
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""