"""GoCube Bluetooth connection and parser."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from ..base import BaseCubeConnection
from ..helpers.cube_math import CubieCube
from ..helpers.state import update_cube_state

_LOGGER = logging.getLogger(__name__)

PRIMARY_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
RX_CHARACTERISTIC_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX_CHARACTERISTIC_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

MSG_TYPE_ROTATION = 0x01
MSG_TYPE_STATE = 0x02
MSG_TYPE_BATTERY = 0x05

WRITE_BATTERY = 0x32
WRITE_STATE = 0x33

CONNECT_TIMEOUT = 20.0

AXIS_PERM = [5, 2, 0, 3, 1, 4]
FACE_PERM = [0, 1, 2, 5, 8, 7, 6, 3]
FACE_OFFSET = [0, 0, 6, 2, 0, 0]


class GoCubeConnection(BaseCubeConnection):
    """Manager for GoCube Bluetooth connection."""

    cube_type = "gocube"
    manufacturer = "GoCube"
    model = "GoCube"
    supports_battery = True

    def __init__(self) -> None:
        super().__init__()
        self._client: Optional[BleakClient] = None
        self._device: Optional[BLEDevice] = None
        self._cube = CubieCube()

    async def connect(self, address: str, device: BLEDevice | None = None) -> None:
        """Connect to the GoCube."""
        async with self._connection_lock:
            await self._cleanup_connection()
            target = device
            if target and target.address.lower() != address.lower():
                target = None
            if target is None:
                raise BleakError("GoCube device not available")

            self._device = target
            _LOGGER.info("Attempting to connect to GoCube...")
            try:
                self._client = await establish_connection(
                    BleakClient,
                    target,
                    "GoCube",
                    disconnected_callback=self._handle_disconnect,
                    timeout=CONNECT_TIMEOUT,
                )
            except Exception as err:
                _LOGGER.warning("GoCube establish_connection failed: %s", err)
                raise
            self._is_connected = True

            await self._client.start_notify(
                TX_CHARACTERISTIC_UUID,
                self._notification_handler,
            )

            await self._request_state()
            self._notify_state_change()

    async def _request_state(self) -> None:
        if not self._client or not self._client.is_connected:
            return
        try:
            await self._client.write_gatt_char(
                RX_CHARACTERISTIC_UUID,
                bytearray([WRITE_STATE]),
            )
        except Exception as err:
            _LOGGER.debug("Failed to request GoCube state: %s", err)

    async def request_battery(self) -> Optional[int]:
        """Request battery level from the cube."""
        if not self._client or not self._client.is_connected:
            return None
        try:
            await self._client.write_gatt_char(
                RX_CHARACTERISTIC_UUID,
                bytearray([WRITE_BATTERY]),
            )
        except Exception as err:
            _LOGGER.debug("Failed to request GoCube battery: %s", err)
            return None
        return self._data.battery_level

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client:
            await self._client.disconnect()
        await self._cleanup_connection()

    async def _cleanup_connection(self) -> None:
        if self._client is not None:
            try:
                try:
                    await self._client.stop_notify(TX_CHARACTERISTIC_UUID)
                except Exception:
                    pass
                await self._client.disconnect()
            except Exception as err:
                _LOGGER.debug("Error during GoCube cleanup: %s", err)
            finally:
                self._client = None
                self._device = None
                self._is_connected = False
                self._notify_state_change()

    def _handle_disconnect(self, client: BleakClient) -> None:
        self._is_connected = False
        self._notify_state_change()
        _LOGGER.debug("GoCube disconnected")

    def _notification_handler(self, sender: int, data: bytearray) -> None:
        if len(data) < 5:
            return
        if data[0] != 0x2A or data[-2:] != b"\x0d\x0a":
            return

        msg_type = data[2]
        if msg_type == MSG_TYPE_ROTATION:
            self._handle_move_message(data)
        elif msg_type == MSG_TYPE_STATE:
            self._handle_state_message(data)
        elif msg_type == MSG_TYPE_BATTERY:
            self._handle_battery_message(data)

    def _handle_move_message(self, data: bytearray) -> None:
        msg_len = len(data) - 6
        if msg_len <= 0:
            return
        for i in range(0, msg_len, 2):
            axis = AXIS_PERM[data[3 + i] >> 1]
            power = 0 if (data[3 + i] & 0x01) == 0 else 2
            suffix = "" if power == 0 else "'"
            notation = f"{'URFDLB'[axis]}{suffix}"
            move_index = axis * 3 + power
            self._cube.apply_move_index(move_index)
            self._data.last_move = notation
            update_cube_state(self._data, self._cube.to_facelet())
            self._touch_activity()
            self._notify_movement(notation)
            self._notify_state_change()
            if i == 0:
                asyncio.create_task(self._request_state())

    def _handle_state_message(self, data: bytearray) -> None:
        if len(data) < 3 + 6 * 9:
            return
        facelet = ["?"] * 54
        for a in range(6):
            axis = AXIS_PERM[a] * 9
            aoff = FACE_OFFSET[a]
            facelet[axis + 4] = "BFUDRL"[data[3 + a * 9]]
            for i in range(8):
                idx = FACE_PERM[(i + aoff) % 8]
                facelet[axis + idx] = "BFUDRL"[data[3 + a * 9 + i + 1]]
        state_string = "".join(facelet)
        self._cube.from_facelet(state_string)
        update_cube_state(self._data, state_string)
        self._touch_activity()
        self._notify_state_change()

    def _handle_battery_message(self, data: bytearray) -> None:
        if len(data) < 5:
            return
        self._data.battery_level = data[3]
        self._notify_state_change()
