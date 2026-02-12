"""Support for BLE Smart Cube switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

DOMAIN = "ble_smartcube"

SWITCH_TYPES: dict[str, SwitchEntityDescription] = {
    "auto_connect": SwitchEntityDescription(
        key="auto_connect",
        name="Auto-Connect",
        has_entity_name=True,
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BLE Smart Cube switches."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    connection = entry_data["connection"]
    async_add_entities(
        SmartCubeAutoConnectSwitch(entry_data, connection, entry, description)
        for description in SWITCH_TYPES.values()
    )


class SmartCubeAutoConnectSwitch(SwitchEntity):
    """Kill switch for auto-connect on advertisements."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_data: dict,
        connection,
        entry: ConfigEntry,
        description: SwitchEntityDescription,
    ) -> None:
        self._entry_data = entry_data
        self.entity_description = description
        self._attr_unique_id = f"{entry.data['address']}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.title,
            "model": connection.model,
            "manufacturer": connection.manufacturer,
        }

    @property
    def is_on(self) -> bool:
        """Return True if auto-connect is enabled."""
        return self._entry_data.get("auto_connect_enabled", True)

    async def async_turn_on(self) -> None:
        """Enable auto-connect on advertisements."""
        setter = self._entry_data.get("set_auto_connect")
        if setter:
            await setter(True)
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Disable auto-connect and disconnect the cube."""
        setter = self._entry_data.get("set_auto_connect")
        if setter:
            await setter(False)
        self.async_write_ha_state()
