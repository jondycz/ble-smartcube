"""Support for BLE Smart Cube sensors."""

from __future__ import annotations

import logging
import time

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    EntityCategory,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartcube_ble.base import BaseCubeConnection

DOMAIN = "ble_smartcube"

_LOGGER = logging.getLogger(__name__)

BATTERY_IDLE_TIMEOUT = 300.0

SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    "battery": SensorEntityDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement="%",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "connection_state": SensorEntityDescription(
        key="connection_state",
        name="Connection State",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "solved_faces": SensorEntityDescription(
        key="solved_faces",
        name="Solved Faces",
        native_unit_of_measurement="faces",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "last_move": SensorEntityDescription(
        key="last_move",
        name="Last Move",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "state_string": SensorEntityDescription(
        key="state_string",
        name="State String",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BLE Smart Cube sensors."""
    connection = hass.data[DOMAIN][entry.entry_id]["connection"]
    async_add_entities(
        SmartCubeSensor(connection, entry, description)
        for description in SENSOR_TYPES.values()
    )


class SmartCubeSensor(SensorEntity):
    """Base class for cube sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        connection: BaseCubeConnection,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.connection = connection
        self.entity_description = description
        self._attr_unique_id = f"{entry.data['address']}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.title,
            "model": connection.model,
            "manufacturer": connection.manufacturer,
        }
        self._unsubscribe = self.connection.register_callback(self._handle_state_change)

    def _handle_state_change(self) -> None:
        """Handle state changes."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True

    @property
    def native_value(self) -> str | int | None:
        """Return the native value."""
        data = self.connection.data
        if self.entity_description.key == "battery":
            return data.battery_level
        if self.entity_description.key == "connection_state":
            return "connected" if self.connection.available else "disconnected"
        if self.entity_description.key == "solved_faces":
            if not data.face_states:
                return 0
            return sum(1 for solved in data.face_states.values() if solved)
        if self.entity_description.key == "last_move":
            return data.last_move
        if self.entity_description.key == "state_string":
            return data.state_string
        return None

    async def async_update(self) -> None:
        """Update the sensor."""
        if not self.available:
            return

        if self.entity_description.key == "battery":
            data = self.connection.data
            if not data.last_move:
                return
            if data.last_update is not None:
                idle_for = time.time() - data.last_update
                if idle_for >= BATTERY_IDLE_TIMEOUT:
                    return
            try:
                await self.connection.request_battery()
            except Exception as err:
                _LOGGER.debug("Failed to request battery: %s", err)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed."""
        self._unsubscribe()

