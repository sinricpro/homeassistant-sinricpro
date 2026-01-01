"""Config flow for SinricPro integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.config_entries import ConfigFlow
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.config_entries import OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinricProApi
from .const import DOMAIN
from .exceptions import SinricProAuthenticationError
from .exceptions import SinricProConnectionError
from .exceptions import SinricProRateLimitError
from .exceptions import SinricProTimeoutError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
    }
)


class SinricProConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SinricPro."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SinricProOptionsFlow:
        """Get the options flow for this handler."""
        return SinricProOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step.

        Args:
            user_input: User input from the form.

        Returns:
            ConfigFlowResult for next step or entry creation.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]

            # Check if this API key is already configured
            await self.async_set_unique_id(api_key)
            self._abort_if_unique_id_configured()

            # Validate the API key
            error = await self._validate_api_key(api_key)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="SinricPro",
                    data={CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication.

        Args:
            entry_data: Existing entry data.

        Returns:
            ConfigFlowResult for the reauth confirm step.
        """
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauthentication confirmation.

        Args:
            user_input: User input from the form.

        Returns:
            ConfigFlowResult for next step or entry update.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]

            # Validate the new API key
            error = await self._validate_api_key(api_key)
            if error:
                errors["base"] = error
            else:
                if self._reauth_entry:
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry,
                        data={CONF_API_KEY: api_key},
                    )
                    await self.hass.config_entries.async_reload(
                        self._reauth_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")
                return self.async_abort(reason="reauth_failed")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "title": self._reauth_entry.title if self._reauth_entry else "SinricPro"
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration.

        Args:
            user_input: User input from the form.

        Returns:
            ConfigFlowResult for next step or entry update.
        """
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]

            # Validate the new API key
            error = await self._validate_api_key(api_key)
            if error:
                errors["base"] = error
            else:
                if entry:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={CONF_API_KEY: api_key},
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _validate_api_key(self, api_key: str) -> str | None:
        """Validate the API key.

        Args:
            api_key: The API key to validate.

        Returns:
            Error key if validation fails, None if successful.
        """
        session = async_get_clientsession(self.hass)
        api = SinricProApi(api_key, session)

        try:
            await api.validate_api_key()
            return None
        except SinricProAuthenticationError:
            _LOGGER.warning("Invalid SinricPro API key")
            return "invalid_auth"
        except SinricProConnectionError:
            _LOGGER.warning("Failed to connect to SinricPro API")
            return "cannot_connect"
        except SinricProTimeoutError:
            _LOGGER.warning("Timeout connecting to SinricPro API")
            return "timeout"
        except SinricProRateLimitError:
            _LOGGER.warning("Rate limit exceeded for SinricPro API")
            return "rate_limit"
        except Exception:
            _LOGGER.exception("Unexpected error validating SinricPro API key")
            return "unknown"


class SinricProOptionsFlow(OptionsFlow):
    """Handle options flow for SinricPro."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow.

        Args:
            config_entry: The config entry.
        """
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options.

        Args:
            user_input: User input from the form.

        Returns:
            ConfigFlowResult for the options.
        """
        # Currently no options, but this can be extended
        return self.async_create_entry(title="", data={})
