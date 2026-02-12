"""Config flow for BLE Smart Cube integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_scanner_count,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
import voluptuous as vol

from .smartcube_ble import match_cube_model

DOMAIN = "ble_smartcube"
CONF_CUBE_TYPE = "cube_type"

_LOGGER = logging.getLogger(__name__)

DISCOVERY_TIMEOUT = 5


class BleSmartCubeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BLE Smart Cube."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovery_cube_type: str | None = None
        self._discovered_devices: dict[str, tuple[BluetoothServiceInfoBleak, str]] = {}

    def _get_cube_type(self, discovery_info: BluetoothServiceInfoBleak) -> str | None:
        """Return the cube type if the device is supported."""
        model = match_cube_model(discovery_info)
        return model.cube_type if model else None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug(
            "Discovered bluetooth device: %s %s",
            discovery_info.name,
            discovery_info.address,
        )

        cube_type = self._get_cube_type(discovery_info)
        if not cube_type:
            return self.async_abort(reason="not_supported_device")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self._discovery_cube_type = cube_type
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name or self._discovery_info.address,
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_CUBE_TYPE: self._discovery_cube_type,
                },
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovery_info.name or self._discovery_info.address,
                "address": self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        if async_scanner_count(self.hass) == 0:
            _LOGGER.warning("No bluetooth scanners available")
            return self.async_abort(reason="bluetooth_not_available")

        _LOGGER.debug("Starting smart cube device discovery...")
        current_addresses = self._async_current_ids()
        if current_addresses:
            _LOGGER.debug("Already configured addresses: %s", current_addresses)

        self._discovered_devices.clear()
        discovered_count = 0

        for discovery_info in async_discovered_service_info(self.hass):
            discovered_count += 1
            if discovery_info.address in current_addresses:
                continue
            if discovery_info.address in self._discovered_devices:
                continue
            cube_type = self._get_cube_type(discovery_info)
            if cube_type:
                self._discovered_devices[discovery_info.address] = (
                    discovery_info,
                    cube_type,
                )

        if not self._discovered_devices:
            _LOGGER.debug("No devices found in first pass, waiting for discovery...")
            await asyncio.sleep(DISCOVERY_TIMEOUT)
            for discovery_info in async_discovered_service_info(self.hass):
                discovered_count += 1
                if discovery_info.address in current_addresses:
                    continue
                if discovery_info.address in self._discovered_devices:
                    continue
                cube_type = self._get_cube_type(discovery_info)
                if cube_type:
                    self._discovered_devices[discovery_info.address] = (
                        discovery_info,
                        cube_type,
                    )

        _LOGGER.debug(
            "Discovery complete. Examined %s devices, found %s smart cube devices",
            discovered_count,
            len(self._discovered_devices),
        )

        if not self._discovered_devices:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors={"base": "no_devices_found"},
                description_placeholders={
                    "title": "No devices found",
                    "description": "Please make sure your cube is turned on and in range.",
                },
            )

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS)
            if address:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                discovery_info, cube_type = self._discovered_devices[address]
                return self.async_create_entry(
                    title=discovery_info.name or discovery_info.address,
                    data={
                        CONF_ADDRESS: address,
                        CONF_CUBE_TYPE: cube_type,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        address: f"{discovery_info.name or address} ({address})"
                        for address, (discovery_info, _cube_type) in self._discovered_devices.items()
                    }
                )
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )

