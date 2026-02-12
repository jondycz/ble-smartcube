"""Support for BLE Smart Cube events."""

from __future__ import annotations

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartcube_ble.base import BaseCubeConnection

DOMAIN = "ble_smartcube"

FACES = ["B", "D", "L", "U", "R", "F"]
EVENT_TYPES = [
    f"{face}{suffix}"
    for face in FACES
    for suffix in ["", "'", "2", "2'"]
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BLE Smart Cube event based on a config entry."""
    connection = hass.data[DOMAIN][entry.entry_id]["connection"]
    async_add_entities([SmartCubeMoveEvent(connection, entry)])


class SmartCubeMoveEvent(EventEntity):
    """Defines a cube move event."""

    _attr_has_entity_name = True
    _attr_name = "Move"
    _attr_device_class = EventDeviceClass.MOTION
    _attr_event_types = EVENT_TYPES

    def __init__(self, connection: BaseCubeConnection, entry: ConfigEntry) -> None:
        """Initialize the event entity."""
        self.connection = connection
        self._attr_unique_id = f"{entry.data['address']}_move"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.title,
            "model": connection.model,
            "manufacturer": connection.manufacturer,
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.connection.add_movement_callback(self._handle_movement)

    def _handle_movement(self, movement: str) -> None:
        """Handle movement events from the cube."""
        if movement in EVENT_TYPES:
            self._trigger_event(movement)
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        self.connection.remove_movement_callback(self._handle_movement)

