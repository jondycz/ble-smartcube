"""GAN cube Bluetooth connection and parser."""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from ..base import BaseCubeConnection
from ..helpers.cube_math import CubieCube
from ..helpers.crypto import AesEcb
from ..helpers.lzstring import decompress_from_encoded_uri_component
from ..helpers.state import update_cube_state

_LOGGER = logging.getLogger(__name__)

UUID_SUFFIX = "-0000-1000-8000-00805f9b34fb"
SERVICE_UUID_META = f"0000180a{UUID_SUFFIX}"
CHRCT_UUID_VERSION = f"00002a28{UUID_SUFFIX}"
CHRCT_UUID_HARDWARE = f"00002a23{UUID_SUFFIX}"
SERVICE_UUID_DATA = f"0000fff0{UUID_SUFFIX}"
CHRCT_UUID_F2 = f"0000fff2{UUID_SUFFIX}"
CHRCT_UUID_F5 = f"0000fff5{UUID_SUFFIX}"
CHRCT_UUID_F6 = f"0000fff6{UUID_SUFFIX}"
CHRCT_UUID_F7 = f"0000fff7{UUID_SUFFIX}"

SERVICE_UUID_V2DATA = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
CHRCT_UUID_V2READ = "28be4cb6-cd67-11e9-a32f-2a2ae2dbcce4"
CHRCT_UUID_V2WRITE = "28be4a4a-cd67-11e9-a32f-2a2ae2dbcce4"

SERVICE_UUID_V3DATA = "8653000a-43e6-47b7-9cb0-5fc21d4ae340"
CHRCT_UUID_V3READ = "8653000b-43e6-47b7-9cb0-5fc21d4ae340"
CHRCT_UUID_V3WRITE = "8653000c-43e6-47b7-9cb0-5fc21d4ae340"

SERVICE_UUID_V4DATA = "00000010-0000-fff7-fff6-fff5fff4fff0"
CHRCT_UUID_V4READ = f"0000fff6{UUID_SUFFIX}"
CHRCT_UUID_V4WRITE = f"0000fff5{UUID_SUFFIX}"

CONNECT_TIMEOUT = 20.0

KEYS = [
    "NoRgnAHANATADDWJYwMxQOxiiEcfYgSK6Hpr4TYCs0IG1OEAbDszALpA",
    "NoNg7ANATFIQnARmogLBRUCs0oAYN8U5J45EQBmFADg0oJAOSlUQF0g",
    "NoRgNATGBs1gLABgQTjCeBWSUDsYBmKbCeMADjNnXxHIoIF0g",
    "NoRg7ANAzBCsAMEAsioxBEIAc0Cc0ATJkgSIYhXIjhMQGxgC6QA",
    "NoVgNAjAHGBMYDYCcdJgCwTFBkYVgAY9JpJYUsYBmAXSA",
    "NoRgNAbAHGAsAMkwgMyzClH0LFcArHnAJzIqIBMGWEAukA",
]


class GanDecoder:
    """AES decoder with optional IV XOR for GAN protocols."""

    def __init__(self, key: List[int], iv: Optional[List[int]] = None) -> None:
        self._aes = AesEcb(key)
        self._iv = iv or []

    def decode(self, data: bytearray) -> List[int]:
        ret = list(data)
        if self._iv:
            if len(ret) > 16:
                offset = len(ret) - 16
                block = self._aes.decrypt_block(ret[offset:])
                for i in range(16):
                    ret[i + offset] = block[i] ^ (self._iv[i] if i < len(self._iv) else 0)
            block = self._aes.decrypt_block(ret[:16])
            for i in range(16):
                ret[i] = block[i] ^ (self._iv[i] if i < len(self._iv) else 0)
            return ret
        return self._aes.decrypt_block(ret[:16]) + ret[16:]

    def encode(self, data: List[int]) -> List[int]:
        ret = list(data)
        if not self._iv:
            block = self._aes.encrypt_block(ret[:16])
            return block + ret[16:]
        for i in range(16):
            ret[i] ^= self._iv[i] if i < len(self._iv) else 0
        ret[:16] = self._aes.encrypt_block(ret[:16])
        if len(ret) > 16:
            offset = len(ret) - 16
            block = ret[offset:]
            for i in range(16):
                block[i] ^= self._iv[i] if i < len(self._iv) else 0
            block = self._aes.encrypt_block(block)
            ret[offset:] = block
        return ret


class GanConnection(BaseCubeConnection):
    """Manager for GAN Bluetooth connection."""

    cube_type = "gan"
    manufacturer = "GAN"
    model = "GAN"
    supports_battery = True

    def __init__(self) -> None:
        super().__init__()
        self._client: Optional[BleakClient] = None
        self._device: Optional[BLEDevice] = None
        self._decoder: Optional[GanDecoder] = None
        self._cube = CubieCube()
        self._version: str | None = None
        self._read_uuid: Optional[str] = None
        self._write_uuid: Optional[str] = None
        self._move_cnt = -1

    async def connect(self, address: str, device: BLEDevice | None = None) -> None:
        async with self._connection_lock:
            await self._cleanup_connection()
            target = device
            if target and target.address.lower() != address.lower():
                target = None
            if target is None:
                raise BleakError("GAN device not available")

            self._device = target
            _LOGGER.info("Attempting to connect to GAN cube...")
            try:
                self._client = await establish_connection(
                    BleakClient,
                    target,
                    "GAN",
                    disconnected_callback=self._handle_disconnect,
                    timeout=CONNECT_TIMEOUT,
                )
            except Exception as err:
                _LOGGER.warning("GAN establish_connection failed: %s", err)
                raise
            self._is_connected = True

            services = await self._client.get_services()
            if services.get_service(SERVICE_UUID_V2DATA):
                await self._init_v2(address)
            elif services.get_service(SERVICE_UUID_V3DATA):
                await self._init_v3(address)
            elif services.get_service(SERVICE_UUID_V4DATA):
                await self._init_v4(address)
            elif services.get_service(SERVICE_UUID_META) and services.get_service(SERVICE_UUID_DATA):
                await self._init_v1()
            else:
                raise BleakError("Unsupported GAN cube services")

            self._notify_state_change()

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
        await self._cleanup_connection()

    async def request_battery(self) -> Optional[int]:
        if self._version == "v2":
            await self._v2_request_battery()
        elif self._version == "v3":
            await self._v3_request_battery()
        elif self._version == "v4":
            await self._v4_request_battery()
        return self._data.battery_level

    async def _cleanup_connection(self) -> None:
        if self._client is not None:
            try:
                if self._read_uuid:
                    try:
                        await self._client.stop_notify(self._read_uuid)
                    except Exception:
                        pass
                await self._client.disconnect()
            except Exception as err:
                _LOGGER.debug("Error during GAN cleanup: %s", err)
            finally:
                self._client = None
                self._device = None
                self._decoder = None
                self._read_uuid = None
                self._write_uuid = None
                self._version = None
                self._is_connected = False
                self._notify_state_change()

    def _handle_disconnect(self, client: BleakClient) -> None:
        self._is_connected = False
        self._notify_state_change()
        _LOGGER.debug("GAN cube disconnected")

    async def _init_v1(self) -> None:
        if not self._client:
            return
        version_value = await self._client.read_gatt_char(CHRCT_UUID_VERSION)
        version = (version_value[0] << 16) | (version_value[1] << 8) | version_value[2]
        hardware_value = await self._client.read_gatt_char(CHRCT_UUID_HARDWARE)
        key_index = (version >> 8) & 0xFF
        if key_index >= len(KEYS):
            raise BleakError("GAN v1 key not available")
        key = json.loads(decompress_from_encoded_uri_component(KEYS[key_index]))
        for i in range(6):
            key[i] = (key[i] + hardware_value[5 - i]) & 0xFF
        self._decoder = GanDecoder(key)
        self._version = "v1"
        self._read_uuid = CHRCT_UUID_F5
        await self._client.start_notify(CHRCT_UUID_F5, self._notification_handler)
        await self._request_v1_state()

    async def _init_v2(self, address: str) -> None:
        self._decoder = GanDecoder(*_get_key_v2(address, ver=0))
        self._version = "v2"
        self._read_uuid = CHRCT_UUID_V2READ
        self._write_uuid = CHRCT_UUID_V2WRITE
        await self._client.start_notify(CHRCT_UUID_V2READ, self._notification_handler)
        await self._v2_request_facelets()
        await self._v2_request_battery()

    async def _init_v3(self, address: str) -> None:
        self._decoder = GanDecoder(*_get_key_v2(address, ver=0))
        self._version = "v3"
        self._read_uuid = CHRCT_UUID_V3READ
        self._write_uuid = CHRCT_UUID_V3WRITE
        await self._client.start_notify(CHRCT_UUID_V3READ, self._notification_handler)
        await self._v3_request_facelets()
        await self._v3_request_battery()

    async def _init_v4(self, address: str) -> None:
        self._decoder = GanDecoder(*_get_key_v2(address, ver=0))
        self._version = "v4"
        self._read_uuid = CHRCT_UUID_V4READ
        self._write_uuid = CHRCT_UUID_V4WRITE
        await self._client.start_notify(CHRCT_UUID_V4READ, self._notification_handler)
        await self._v4_request_facelets()
        await self._v4_request_battery()

    async def _send_request(self, payload: List[int]) -> None:
        if not self._client or not self._write_uuid or not self._decoder:
            return
        encoded = self._decoder.encode(payload)
        await self._client.write_gatt_char(self._write_uuid, bytearray(encoded))

    async def _v2_request_facelets(self) -> None:
        req = [0] * 20
        req[0] = 4
        await self._send_request(req)

    async def _v2_request_battery(self) -> None:
        req = [0] * 20
        req[0] = 9
        await self._send_request(req)

    async def _v3_request_facelets(self) -> None:
        req = [0] * 16
        req[0] = 0x68
        req[1] = 1
        await self._send_request(req)

    async def _v3_request_battery(self) -> None:
        req = [0] * 16
        req[0] = 0x68
        req[1] = 7
        await self._send_request(req)

    async def _v4_request_facelets(self) -> None:
        req = [0] * 20
        req[0] = 0xDD
        req[1] = 0x04
        req[3] = 0xED
        await self._send_request(req)

    async def _v4_request_battery(self) -> None:
        req = [0] * 20
        req[0] = 0xDF
        req[1] = 0x03
        await self._send_request(req)

    async def _request_v1_state(self) -> None:
        if not self._client or not self._decoder:
            return
        raw = await self._client.read_gatt_char(CHRCT_UUID_F2)
        decoded = self._decoder.decode(raw)
        state = []
        for i in range(0, len(decoded) - 2, 3):
            face = decoded[i ^ 1] << 16 | decoded[i + 1 ^ 1] << 8 | decoded[i + 2 ^ 1]
            for j in range(21, -1, -3):
                state.append("URFDLB"[(face >> j) & 0x7])
                if j == 12:
                    state.append("URFDLB"[i // 3])
        update_cube_state(self._data, "".join(state))
        self._cube.from_facelet(self._data.state_string or "")

    def _notification_handler(self, sender: int, data: bytearray) -> None:
        if not self._decoder:
            return
        decoded = self._decoder.decode(data)
        bits = "".join(f"{b:08b}" for b in decoded)
        if self._version == "v2":
            self._parse_v2(bits)
        elif self._version == "v3":
            self._parse_v3(bits)
        elif self._version == "v4":
            self._parse_v4(bits)
        elif self._version == "v1":
            self._parse_v1(decoded)

    def _parse_v1(self, decoded: List[int]) -> None:
        move_cnt = decoded[12]
        if move_cnt == self._move_cnt:
            return
        self._move_cnt = move_cnt
        for i in range(6):
            m = decoded[13 + i]
            face = "URFDLB"[m // 3]
            suffix = ["", "2", "'"][m % 3]
            move = face + suffix
            axis = "URFDLB".find(face)
            power = 2 if suffix == "'" else 0
            self._cube.apply_move_index(axis * 3 + power)
            if suffix == "2":
                self._cube.apply_move_index(axis * 3 + power)
            self._data.last_move = move
            update_cube_state(self._data, self._cube.to_facelet())
            self._notify_movement(move)
        self._touch_activity()
        self._notify_state_change()

    def _parse_v2(self, bits: str) -> None:
        mode = int(bits[0:4], 2)
        if mode == 2:
            move_cnt = int(bits[4:12], 2)
            if move_cnt == self._move_cnt or self._move_cnt == -1:
                self._move_cnt = move_cnt
                return
            moves = []
            for i in range(7):
                m = int(bits[12 + i * 5 : 17 + i * 5], 2)
                if m >= 12:
                    continue
                face = "URFDLB"[m >> 1]
                suffix = "'" if (m & 1) else ""
                moves.append(face + suffix)
            self._apply_moves(moves)
            self._move_cnt = move_cnt
        elif mode == 4:
            facelet = _parse_gan_facelet(bits, 12, 33, 47, 91)
            if facelet:
                self._cube.from_facelet(facelet)
                update_cube_state(self._data, facelet)
                self._touch_activity()
                self._notify_state_change()
        elif mode == 9:
            self._data.battery_level = int(bits[8:16], 2)
            self._notify_state_change()

    def _parse_v3(self, bits: str) -> None:
        if int(bits[0:8], 2) != 0x55:
            return
        mode = int(bits[8:16], 2)
        if mode == 1:
            move_cnt = int(bits[64:72] + bits[56:64], 2)
            if move_cnt == self._move_cnt or self._move_cnt == -1:
                self._move_cnt = move_cnt
                return
            pow_bits = int(bits[72:74], 2)
            axis_bits = int(bits[74:80], 2)
            axis = [2, 32, 8, 1, 16, 4].index(axis_bits)
            if axis >= 0:
                suffix = "'" if pow_bits == 1 else ""
                move = f"{'URFDLB'[axis]}{suffix}"
                self._apply_moves([move])
            self._move_cnt = move_cnt
        elif mode == 2:
            facelet = _parse_gan_facelet(bits, 40, 61, 77, 121)
            if facelet:
                self._cube.from_facelet(facelet)
                update_cube_state(self._data, facelet)
                self._touch_activity()
                self._notify_state_change()
        elif mode == 16:
            self._data.battery_level = int(bits[24:32], 2)
            self._notify_state_change()

    def _parse_v4(self, bits: str) -> None:
        mode = int(bits[0:8], 2)
        if mode == 0x01:
            move_cnt = int(bits[56:64] + bits[48:56], 2)
            if move_cnt == self._move_cnt or self._move_cnt == -1:
                self._move_cnt = move_cnt
                return
            pow_bits = int(bits[64:66], 2)
            axis_bits = int(bits[66:72], 2)
            axis = [2, 32, 8, 1, 16, 4].index(axis_bits)
            if axis >= 0:
                suffix = "'" if pow_bits == 1 else ""
                move = f"{'URFDLB'[axis]}{suffix}"
                self._apply_moves([move])
            self._move_cnt = move_cnt
        elif mode == 0xED:
            facelet = _parse_gan_facelet(bits, 32, 53, 69, 113)
            if facelet:
                self._cube.from_facelet(facelet)
                update_cube_state(self._data, facelet)
                self._touch_activity()
                self._notify_state_change()
        elif mode == 0xEF:
            length = int(bits[8:16], 2)
            self._data.battery_level = int(bits[8 + length * 8 : 16 + length * 8], 2)
            self._notify_state_change()

    def _apply_moves(self, moves: List[str]) -> None:
        if not moves:
            return
        for move in reversed(moves):
            axis = "URFDLB".find(move[0])
            if axis == -1:
                continue
            power = 2 if move.endswith("'") else 0
            self._cube.apply_move_index(axis * 3 + power)
            self._data.last_move = move
            update_cube_state(self._data, self._cube.to_facelet())
            self._notify_movement(move)
        self._touch_activity()
        self._notify_state_change()


def _get_key_v2(address: str, ver: int) -> tuple[List[int], List[int]]:
    mac = [int(part, 16) for part in address.split(":") if part]
    if len(mac) != 6:
        return [], []
    key = json.loads(decompress_from_encoded_uri_component(KEYS[2 + ver * 2]))
    iv = json.loads(decompress_from_encoded_uri_component(KEYS[3 + ver * 2]))
    for i in range(6):
        key[i] = (key[i] + mac[5 - i]) % 255
        iv[i] = (iv[i] + mac[5 - i]) % 255
    return key, iv


def _parse_gan_facelet(bits: str, corner_perm_start: int, corner_ori_start: int, edge_perm_start: int, edge_ori_start: int) -> str | None:
    cc = CubieCube()
    cchk = 0xF00
    for i in range(7):
        perm = int(bits[corner_perm_start + i * 3 : corner_perm_start + i * 3 + 3], 2)
        ori = int(bits[corner_ori_start + i * 2 : corner_ori_start + i * 2 + 2], 2)
        cchk -= ori << 3
        cchk ^= perm
        cc.ca[i] = (ori << 3) | perm
    cc.ca[7] = (cchk & 0xFF8) % 24 | (cchk & 0x7)

    echk = 0
    for i in range(11):
        perm = int(bits[edge_perm_start + i * 4 : edge_perm_start + i * 4 + 4], 2)
        ori = int(bits[edge_ori_start + i : edge_ori_start + i + 1], 2)
        echk ^= (perm << 1) | ori
        cc.ea[i] = (perm << 1) | ori
    cc.ea[11] = echk
    return cc.to_facelet()
