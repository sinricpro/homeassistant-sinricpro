"""SinricPro base entity class."""
from __future__ import annotations

from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class SinricProEntity(Entity):
    """Base class for SinricPro entities."""

    _attr_should_poll = False

    def __init__(self, device_id: str, name: str) -> None:
        """Initialize the entity."""
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_available = True

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._attr_name,
            "manufacturer": "SinricPro",
            "model": "SinricPro Device",
            "sw_version": "1.0.0",
        }