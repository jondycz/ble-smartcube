"""The BLE Smart Cube integration."""

from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.typing import ConfigType

from bleak.backends.device import BLEDevice

from .smartcube_ble import create_connection, get_cube_model

DOMAIN = "ble_smartcube"
CONF_CUBE_TYPE = "cube_type"

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["binary_sensor", "sensor", "event", "switch"]

RECONNECT_RETRY_SECONDS = 2.5
RECONNECT_RETRY_WINDOW = 15.0
WAIT_FOR_ADV_SECONDS = 5.0


class SmartCubeError(HomeAssistantError):
    """Base class for BLE Smart Cube errors."""


class SmartCubeConnectionError(SmartCubeError):
    """Raised when there is an error connecting to the cube."""


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BLE Smart Cube from a config entry."""
    entry_cube_type = entry.data.get(CONF_CUBE_TYPE, "")
    cube_model = get_cube_model(entry_cube_type)
    connection = create_connection(cube_model.cube_type)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "connection": connection,
        "unsub_ble": None,
        "auto_connect_enabled": True,
        "set_auto_connect": None,
        "cube_model": cube_model,
    }
    entry_data = hass.data[DOMAIN][entry.entry_id]

    connect_state = {
        "in_progress": False,
        "retry_task": None,
        "last_advertisement": None,
        "reconnect_task": None,
    }

    async def _get_ble_device(address: str) -> BLEDevice | None:
        try:
            return await bluetooth.async_ble_device_from_address(
                hass,
                address,
                True,
            )
        except TypeError:
            try:
                return await bluetooth.async_ble_device_from_address(hass, address)
            except Exception as err:
                _LOGGER.debug("BLE device lookup failed: %s", err)
        except Exception as err:
            _LOGGER.debug("BLE device lookup failed: %s", err)
        try:
            service_info = bluetooth.async_last_service_info(hass, address, True)
            if service_info is not None:
                return service_info.device
        except Exception as err:
            _LOGGER.debug("BLE service info lookup failed: %s", err)
        try:
            def _match_address(service_info: BluetoothServiceInfoBleak) -> bool:
                return service_info.address.lower() == address.lower()

            service_info = await bluetooth.async_process_advertisements(
                hass,
                _match_address,
                {"address": address, "connectable": True},
                BluetoothScanningMode.ACTIVE,
                WAIT_FOR_ADV_SECONDS,
            )
            if service_info is not None:
                return service_info.device
        except Exception as err:
            _LOGGER.debug("BLE advertisement wait failed: %s", err)
        return None

    async def _async_try_connect(
        reason: str,
        device: BLEDevice | None = None,
    ) -> None:
        if not entry_data["auto_connect_enabled"]:
            return
        if connect_state["in_progress"]:
            return
        if connection.available:
            return
        connect_state["in_progress"] = True
        try:
            address = entry.data["address"]
            device_to_use = None
            if device and device.address.lower() == address.lower():
                device_to_use = device
            if device_to_use is None:
                device_to_use = await _get_ble_device(address)
            await connection.connect(address, device=device_to_use)
            try:
                await connection.request_battery()
            except Exception as err:
                _LOGGER.debug("Initial battery request failed: %s", err)
        except Exception as err:
            _LOGGER.warning("Cube connect failed (%s): %s", reason, err)
            _LOGGER.debug("Cube connect exception", exc_info=err)
            _schedule_retry()
        finally:
            connect_state["in_progress"] = False

    def _schedule_retry() -> None:
        if not entry_data["auto_connect_enabled"]:
            return
        if connect_state["retry_task"] is not None:
            return
        last_adv = connect_state["last_advertisement"]
        if last_adv is None:
            return

        async def _retry() -> None:
            await asyncio.sleep(RECONNECT_RETRY_SECONDS)
            connect_state["retry_task"] = None
            if not entry_data["auto_connect_enabled"]:
                return
            last_seen = connect_state["last_advertisement"]
            if last_seen is None:
                return
            if time.monotonic() - last_seen > RECONNECT_RETRY_WINDOW:
                return
            if connection.available:
                return
            await _async_try_connect("retry")

        connect_state["retry_task"] = hass.async_create_task(_retry())

    def _handle_advertisement(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        if not entry_data["auto_connect_enabled"]:
            return
        if connection.available:
            return
        if connection._connection_lock.locked() or connect_state["in_progress"]:
            return
        connect_state["last_advertisement"] = time.monotonic()
        hass.async_create_task(
            _async_try_connect("advertisement", device=service_info.device)
        )

    last_available = {"state": connection.available}

    def _handle_connection_state() -> None:
        now_available = connection.available
        was_available = last_available["state"]
        last_available["state"] = now_available
        if now_available or not was_available:
            return
        if not entry_data["auto_connect_enabled"]:
            return
        if connect_state["reconnect_task"] is not None:
            return

        async def _reconnect() -> None:
            try:
                await _async_try_connect("disconnect")
            finally:
                connect_state["reconnect_task"] = None

        connect_state["reconnect_task"] = hass.async_create_task(_reconnect())

    async def _set_auto_connect(enabled: bool) -> None:
        entry_data["auto_connect_enabled"] = enabled
        unsub = entry_data.get("unsub_ble")
        if not enabled:
            if unsub:
                unsub()
                entry_data["unsub_ble"] = None
            await connection.disconnect()
            return
        if unsub is None:
            matcher = BluetoothCallbackMatcher(address=entry.data["address"])
            entry_data["unsub_ble"] = bluetooth.async_register_callback(
                hass,
                _handle_advertisement,
                matcher,
                BluetoothScanningMode.ACTIVE,
            )
        hass.async_create_task(_async_try_connect("enable"))

    entry_data["set_auto_connect"] = _set_auto_connect
    entry_data["unsub_state"] = connection.register_callback(_handle_connection_state)

    await _set_auto_connect(True)
    await _async_try_connect("startup")
    if not connection.available:
        _LOGGER.debug(
            "Cube not available at startup (will retry on advertisements)."
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        try:
            entry_data = hass.data[DOMAIN][entry.entry_id]
            set_auto_connect = entry_data.get("set_auto_connect")
            if set_auto_connect:
                await set_auto_connect(False)
            else:
                unsub = entry_data.get("unsub_ble")
                if unsub:
                    unsub()
                unsub_state = entry_data.get("unsub_state")
                if unsub_state:
                    unsub_state()
                connection = entry_data["connection"]
                await connection.disconnect()
        except Exception as err:
            _LOGGER.error("Error disconnecting from cube: %s", err)
        finally:
            hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the BLE Smart Cube integration."""
    return True

