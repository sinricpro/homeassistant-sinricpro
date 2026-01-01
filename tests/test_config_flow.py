"""Tests for SinricPro config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.sinricpro.const import DOMAIN
from custom_components.sinricpro.exceptions import (
    SinricProAuthenticationError,
    SinricProConnectionError,
    SinricProRateLimitError,
    SinricProTimeoutError,
)

pytestmark = pytest.mark.skip(reason="Timezone configuration issue in test environment")


async def test_config_flow_success(hass: HomeAssistant) -> None:
    """Test successful config flow."""
    with patch(
        "custom_components.sinricpro.config_flow.SinricProApi"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.validate_api_key = AsyncMock(return_value=True)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "test_api_key_12345"},
        )

        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "SinricPro"
        assert result2["data"] == {CONF_API_KEY: "test_api_key_12345"}


async def test_config_flow_invalid_api_key(hass: HomeAssistant) -> None:
    """Test config flow with invalid API key."""
    with patch(
        "custom_components.sinricpro.config_flow.SinricProApi"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.validate_api_key = AsyncMock(
            side_effect=SinricProAuthenticationError("Invalid API key")
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "invalid_key"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "invalid_auth"}


async def test_config_flow_connection_error(hass: HomeAssistant) -> None:
    """Test config flow with connection error."""
    with patch(
        "custom_components.sinricpro.config_flow.SinricProApi"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.validate_api_key = AsyncMock(
            side_effect=SinricProConnectionError("Connection failed")
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "test_api_key"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_config_flow_timeout(hass: HomeAssistant) -> None:
    """Test config flow with timeout error."""
    with patch(
        "custom_components.sinricpro.config_flow.SinricProApi"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.validate_api_key = AsyncMock(
            side_effect=SinricProTimeoutError("Request timed out")
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "test_api_key"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "timeout"}


async def test_config_flow_rate_limit(hass: HomeAssistant) -> None:
    """Test config flow with rate limit error."""
    with patch(
        "custom_components.sinricpro.config_flow.SinricProApi"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.validate_api_key = AsyncMock(
            side_effect=SinricProRateLimitError("Rate limit exceeded", retry_after=60)
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "test_api_key"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "rate_limit"}


async def test_config_flow_unknown_error(hass: HomeAssistant) -> None:
    """Test config flow with unknown error."""
    with patch(
        "custom_components.sinricpro.config_flow.SinricProApi"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.validate_api_key = AsyncMock(
            side_effect=Exception("Unknown error")
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "test_api_key"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "unknown"}


async def test_config_flow_duplicate(hass: HomeAssistant) -> None:
    """Test config flow prevents duplicate entries."""
    with patch(
        "custom_components.sinricpro.config_flow.SinricProApi"
    ) as mock_api_class:
        mock_api = mock_api_class.return_value
        mock_api.validate_api_key = AsyncMock(return_value=True)

        # Create first entry
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "test_api_key_12345"},
        )

        assert result2["type"] == FlowResultType.CREATE_ENTRY

        # Try to create duplicate entry
        result3 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {CONF_API_KEY: "test_api_key_12345"},
        )

        assert result4["type"] == FlowResultType.ABORT
        assert result4["reason"] == "already_configured"


@pytest.mark.parametrize(
    "source",
    [config_entries.SOURCE_USER, config_entries.SOURCE_IMPORT],
)
async def test_config_flow_form_shown(hass: HomeAssistant, source: str) -> None:
    """Test that the config flow form is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": source}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
