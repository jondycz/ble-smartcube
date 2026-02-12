"""QiYi cube Bluetooth connection and parser."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from ..base import BaseCubeConnection
from ..helpers.crypto import AesEcb
from ..helpers.lzstring import decompress_from_encoded_uri_component
from ..helpers.state import update_cube_state

_LOGGER = logging.getLogger(__name__)

UUID_SUFFIX = "-0000-1000-8000-00805f9b34fb"
SERVICE_UUID = f"0000fff0{UUID_SUFFIX}"
CHRCT_UUID_CUBE = f"0000fff6{UUID_SUFFIX}"

CONNECT_TIMEOUT = 20.0

KEYS = ["NoDg7ANAjGkEwBYCc0xQnADAVgkzGAzHNAGyRTanQi5QIFyHrjQMQgsC6QA"]


class QiYiConnection(BaseCubeConnection):
    """Manager for QiYi Bluetooth connection."""

    cube_type = "qiyi"
    manufacturer = "QiYi"
    model = "QiYi"
    supports_battery = True

    def __init__(self) -> None:
        super().__init__()
        self._client: Optional[BleakClient] = None
        self._device: Optional[BLEDevice] = None
        self._decoder: Optional[AesEcb] = None

    async def connect(self, address: str, device: BLEDevice | None = None) -> None:
        async with self._connection_lock:
            await self._cleanup_connection()
            target = device
            if target and target.address.lower() != address.lower():
                target = None
            if target is None:
                raise BleakError("QiYi device not available")

            self._device = target
            _LOGGER.info("Attempting to connect to QiYi cube...")
            try:
                self._client = await establish_connection(
                    BleakClient,
                    target,
                    "QiYi",
                    disconnected_callback=self._handle_disconnect,
                    timeout=CONNECT_TIMEOUT,
                )
            except Exception as err:
                _LOGGER.warning("QiYi establish_connection failed: %s", err)
                raise
            self._is_connected = True

            key = json.loads(decompress_from_encoded_uri_component(KEYS[0]))
            self._decoder = AesEcb(key)

            await self._client.start_notify(CHRCT_UUID_CUBE, self._notification_handler)
            await self._send_hello(address)
            self._notify_state_change()

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
        await self._cleanup_connection()

    async def request_battery(self) -> Optional[int]:
        return self._data.battery_level

    async def _cleanup_connection(self) -> None:
        if self._client is not None:
            try:
                try:
                    await self._client.stop_notify(CHRCT_UUID_CUBE)
                except Exception:
                    pass
                await self._client.disconnect()
            except Exception as err:
                _LOGGER.debug("Error during QiYi cleanup: %s", err)
            finally:
                self._client = None
                self._device = None
                self._decoder = None
                self._is_connected = False
                self._notify_state_change()

    def _handle_disconnect(self, client: BleakClient) -> None:
        self._is_connected = False
        self._notify_state_change()
        _LOGGER.debug("QiYi cube disconnected")

    async def _send_hello(self, address: str) -> None:
        if not self._client or not self._client.is_connected:
            return
        mac = [int(part, 16) for part in address.split(":") if part]
        if len(mac) != 6:
            return
        content = [0x00, 0x6B, 0x01, 0x00, 0x00, 0x22, 0x06, 0x00, 0x02, 0x08, 0x00]
        for i in range(5, -1, -1):
            content.append(mac[i])
        await self._send_message(content)

    async def _send_message(self, content: List[int]) -> None:
        if not self._client or not self._client.is_connected or self._decoder is None:
            return
        msg = [0xFE]
        msg.append(4 + len(content))
        msg.extend(content)
        crc = _crc16_modbus(msg)
        msg.append(crc & 0xFF)
        msg.append((crc >> 8) & 0xFF)
        pad = (16 - len(msg) % 16) % 16
        msg.extend([0] * pad)
        enc: List[int] = []
        for i in range(0, len(msg), 16):
            block = self._decoder.encrypt_block(msg[i : i + 16])
            enc.extend(block)
        await self._client.write_gatt_char(CHRCT_UUID_CUBE, bytearray(enc))

    def _notification_handler(self, sender: int, data: bytearray) -> None:
        if self._decoder is None:
            return
        enc = list(data)
        msg: List[int] = []
        for i in range(0, len(enc), 16):
            block = self._decoder.decrypt_block(enc[i : i + 16])
            msg.extend(block)
        msg = msg[: msg[1]] if len(msg) > 1 else msg
        if len(msg) < 3 or _crc16_modbus(msg) != 0:
            return
        self._parse_message(msg)

    def _parse_message(self, msg: List[int]) -> None:
        if msg[0] != 0xFE:
            return
        opcode = msg[2]
        if opcode in (0x02, 0x03):
            self._send_ack(msg[2:7])
        if opcode == 0x02:
            self._data.battery_level = msg[35]
            facelet = _parse_facelet(msg[7:34])
            update_cube_state(self._data, facelet)
            self._touch_activity()
            self._notify_state_change()
            return
        if opcode == 0x03:
            facelet = _parse_facelet(msg[7:34])
            update_cube_state(self._data, facelet)
            move = _parse_move(msg[34])
            if move:
                self._data.last_move = move
                self._notify_movement(move)
            self._touch_activity()
            self._notify_state_change()

    def _send_ack(self, payload: List[int]) -> None:
        if not payload:
            return
        asyncio.create_task(self._send_message(payload))


def _crc16_modbus(data: List[int]) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _parse_facelet(face_msg: List[int]) -> str:
    ret: List[str] = []
    for i in range(54):
        val = face_msg[i >> 1] >> ((i % 2) * 4)
        ret.append("LRDUFB"[val & 0xF])
    return "".join(ret)


def _parse_move(raw: int) -> str | None:
    if raw <= 0:
        return None
    axis = [4, 1, 3, 0, 2, 5][(raw - 1) >> 1]
    power = [0, 2][raw & 1]
    suffix = "" if power == 0 else "'"
    return f"{'URFDLB'[axis]}{suffix}"
