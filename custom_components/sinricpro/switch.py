"""SinricPro switch platform."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .entity import SinricProEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SinricPro switches."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    client = entry_data["client"]
    
    # Get all switch devices from SinricPro
    devices = client.get_devices().get("switch", {})
    
    if not devices:
        _LOGGER.info("No switch devices found in SinricPro account")
        return
    
    # Create update coordinator
    async def async_update_data():
        """Fetch data from API endpoint."""
        all_states = {}
        for device_id in devices:
            state = await client.get_device_state(device_id)
            all_states[device_id] = state
        return all_states
    
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sinricpro_switch",
        update_method=async_update_data,
        update_interval=None,  # We'll update it manually using SSE events
    )
    
    # Fetch initial data
    await coordinator.async_refresh()
    
    switches = []
    for device_id, device_data in devices.items():
        switch = SinricProSwitch(
            coordinator=coordinator,
            device_id=device_id,
            name=device_data.get("name", f"Switch {device_id}"),
            client=client,
            device_data=device_data
        )
        
        switches.append(switch)
    
    async_add_entities(switches)


class SinricProSwitch(CoordinatorEntity, SinricProEntity, SwitchEntity):
    """Representation of a SinricPro switch."""

    def __init__(self, coordinator, device_id: str, name: str, client, device_data: Dict[str, Any]) -> None:
        """Initialize the switch."""
        CoordinatorEntity.__init__(self, coordinator)
        SinricProEntity.__init__(self, device_id, name)
        self._client = client
        self._device_data = device_data
        self._attr_available = True
        
        # Register callback for SSE events
        self._client.register_callback(device_id, self._handle_device_event)

    async def _handle_device_event(self, event_data: Dict[str, Any]) -> None:
        """Handle device events from SinricPro SSE."""
        _LOGGER.debug("Received event for %s: %s", self._device_id, event_data)
        
        # Handle availability changes
        if "available" in event_data:
            self._attr_available = event_data["available"]
            self.async_write_ha_state()
            return
            
        # Handle state changes
        if "powerState" in event_data:
            # Update coordinator data
            if self._device_id in self.coordinator.data:
                self.coordinator.data[self._device_id]["powerState"] = event_data["powerState"]
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if not self.coordinator.data or self._device_id not in self.coordinator.data:
            return False
            
        device_state = self.coordinator.data[self._device_id]
        power_state = device_state.get("powerState", "Off")
        # Case insensitive comparison for flexibility
        return power_state.lower() == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        state = {"powerState": "On"}
        success = await self._client.set_device_state(self._device_id, state)
        
        if success:
            # Update coordinator data
            if self._device_id in self.coordinator.data:
                self.coordinator.data[self._device_id]["powerState"] = "On"
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        state = {"powerState": "Off"}
        success = await self._client.set_device_state(self._device_id, state)
        
        if success:
            # Update coordinator data
            if self._device_id in self.coordinator.data:
                self.coordinator.data[self._device_id]["powerState"] = "Off"
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity."""
        await self.coordinator.async_request_refresh()
        
    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # Unregister callback when entity is removed
        self._client.unregister_callback(self._device_id, self._handle_device_event)