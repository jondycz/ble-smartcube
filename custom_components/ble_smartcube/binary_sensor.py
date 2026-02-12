"""Support for BLE Smart Cube binary sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .smartcube_ble.base import BaseCubeConnection

DOMAIN = "ble_smartcube"

BINARY_SENSOR_TYPES: dict[str, BinarySensorEntityDescription] = {
    "cube_solved": BinarySensorEntityDescription(
        key="cube_solved",
        name="Solved",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "blue_face": BinarySensorEntityDescription(
        key="blue_face",
        name="Blue Face",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "green_face": BinarySensorEntityDescription(
        key="green_face",
        name="Green Face",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "white_face": BinarySensorEntityDescription(
        key="white_face",
        name="White Face",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "yellow_face": BinarySensorEntityDescription(
        key="yellow_face",
        name="Yellow Face",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "red_face": BinarySensorEntityDescription(
        key="red_face",
        name="Red Face",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    "orange_face": BinarySensorEntityDescription(
        key="orange_face",
        name="Orange Face",
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BLE Smart Cube binary sensors."""
    connection = hass.data[DOMAIN][entry.entry_id]["connection"]
    async_add_entities(
        SmartCubeBinarySensor(connection, entry, description)
        for description in BINARY_SENSOR_TYPES.values()
    )


class SmartCubeBinarySensor(BinarySensorEntity):
    """Representation of a cube binary sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        connection: BaseCubeConnection,
        entry: ConfigEntry,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        self.connection = connection
        self.entity_description = description
        self._attr_unique_id = f"{entry.data['address']}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.title,
            "model": connection.model,
            "manufacturer": connection.manufacturer,
        }
        self._unsubscribe = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self._unsubscribe = self.connection.register_callback(self._handle_state_change)

    def _handle_state_change(self) -> None:
        """Handle state changes."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return if the face is solved."""
        data = self.connection.data
        if self.entity_description.key == "cube_solved":
            return data.is_solved

        color = self.entity_description.key.split("_")[0].capitalize()
        return data.face_states.get(color, False)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._unsubscribe:
            self._unsubscribe()

