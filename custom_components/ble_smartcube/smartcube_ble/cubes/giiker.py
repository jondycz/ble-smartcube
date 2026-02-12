"""Connection management for Giiker."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from ..base import BaseCubeConnection
from ..helpers.state import COLOR_FACE_MAPPING, FACE_TILE_INDICES
from ..models import CubeData

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10.0

PRIMARY_SERVICE_UUID = "0000aadb-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000aadc-0000-1000-8000-00805f9b34fb"

SYSTEM_SERVICE_UUID = "0000aaaa-0000-1000-8000-00805f9b34fb"
SYSTEM_READ_UUID = "0000aaab-0000-1000-8000-00805f9b34fb"
SYSTEM_WRITE_UUID = "0000aaac-0000-1000-8000-00805f9b34fb"

DECRYPTION_KEY = bytes(
    [
        176,
        81,
        104,
        224,
        86,
        137,
        237,
        119,
        38,
        26,
        193,
        161,
        210,
        126,
        150,
        81,
        93,
        13,
        236,
        249,
        89,
        235,
        88,
        24,
        113,
        81,
        214,
        131,
        130,
        199,
        2,
        169,
        39,
        165,
        171,
        41,
    ]
)

FACES = ["B", "D", "L", "U", "R", "F"]
COLORS = ["blue", "yellow", "orange", "white", "red", "green"]

TURN_AMOUNTS = {
    0: 1,
    1: 2,
    2: -1,
    8: -2,
}

CORNER_COLORS = [
    [1, 4, 5],
    [4, 3, 5],
    [3, 2, 5],
    [2, 1, 5],
    [4, 1, 0],
    [3, 4, 0],
    [2, 3, 0],
    [1, 2, 0],
]

CORNER_LOCATIONS = [
    [1, 4, 5],
    [4, 3, 5],
    [3, 2, 5],
    [2, 1, 5],
    [4, 1, 0],
    [3, 4, 0],
    [2, 3, 0],
    [1, 2, 0],
]

EDGE_LOCATIONS = [
    [5, 1],
    [5, 4],
    [5, 3],
    [5, 2],
    [1, 4],
    [3, 4],
    [3, 2],
    [1, 2],
    [0, 1],
    [0, 4],
    [0, 3],
    [0, 2],
]

EDGE_COLORS = [
    [5, 1],
    [5, 4],
    [5, 3],
    [5, 2],
    [1, 4],
    [3, 4],
    [3, 2],
    [1, 2],
    [0, 1],
    [0, 4],
    [0, 3],
    [0, 2],
]

CORNER_FACE_INDICES = [
    [29, 15, 26],
    [9, 8, 20],
    [6, 38, 18],
    [44, 27, 24],
    [17, 35, 51],
    [2, 11, 45],
    [36, 0, 47],
    [33, 42, 53],
]

EDGE_FACE_INDICES = [
    [25, 28],
    [23, 12],
    [19, 7],
    [21, 41],
    [32, 16],
    [5, 10],
    [3, 37],
    [30, 43],
    [52, 34],
    [48, 14],
    [46, 1],
    [50, 39],
]

class GiikerDataParser:
    """Parser for Giiker data."""

    def __init__(self, data: CubeData | None = None) -> None:
        """Initialize the parser."""
        self.data = data or CubeData()

    def parse_cube_value(self, raw: bytes) -> str | None:
        """Parse cube notification data and return last move notation."""
        if not raw:
            return None

        self.data.last_raw = bytes(raw)

        data = bytearray(raw)
        if self._is_encrypted(data):
            self._decrypt_in_place(data)

        self.data.last_decrypted = bytes(data)

        state, moves = self._parse_cube_payload(data)
        state_string, face_states, is_solved = self._build_state(state)

        self.data.state_string = state_string
        self.data.face_states = face_states
        self.data.is_solved = is_solved
        self.data.last_update = time.time()

        last_move = moves[0]["notation"] if moves else None
        if last_move:
            self.data.last_move = last_move
        return last_move

    def parse_battery_value(self, raw: bytes) -> None:
        """Parse battery value from the system service notification."""
        if len(raw) < 2:
            return
        self.data.battery_level = raw[1]

    def _is_encrypted(self, data: bytearray) -> bool:
        """Return True if data looks encrypted."""
        return len(data) >= 19 and data[18] == 0xA7

    def _decrypt_in_place(self, data: bytearray) -> None:
        """Decrypt data in place using the Giiker key."""
        if len(data) < 20:
            return

        offset1 = self._get_nibble(data, 38)
        offset2 = self._get_nibble(data, 39)

        for i in range(20):
            index1 = (offset1 + i) % len(DECRYPTION_KEY)
            index2 = (offset2 + i) % len(DECRYPTION_KEY)
            data[i] = (data[i] + DECRYPTION_KEY[index1] + DECRYPTION_KEY[index2]) & 0xFF

    def _get_nibble(self, data: bytearray, index: int) -> int:
        """Get the nibble at index from the data."""
        byte_val = data[index // 2]
        if index % 2 == 1:
            return byte_val & 0x0F
        return (byte_val >> 4) & 0x0F

    def _parse_cube_payload(self, data: bytearray) -> Tuple[Dict[str, list[int]], list[dict[str, Any]]]:
        """Parse the cube payload into state and move list."""
        state = {
            "corner_positions": [],
            "corner_orientations": [],
            "edge_positions": [],
            "edge_orientations": [],
        }
        moves: list[dict[str, Any]] = []

        for i, move in enumerate(data):
            high_nibble = move >> 4
            low_nibble = move & 0x0F

            if i < 4:
                state["corner_positions"].extend([high_nibble, low_nibble])
            elif i < 8:
                state["corner_orientations"].extend([high_nibble, low_nibble])
            elif i < 14:
                state["edge_positions"].extend([high_nibble, low_nibble])
            elif i < 16:
                state["edge_orientations"].append(bool(move & 0x80))
                state["edge_orientations"].append(bool(move & 0x40))
                state["edge_orientations"].append(bool(move & 0x20))
                state["edge_orientations"].append(bool(move & 0x10))
                if i == 14:
                    state["edge_orientations"].append(bool(move & 0x08))
                    state["edge_orientations"].append(bool(move & 0x04))
                    state["edge_orientations"].append(bool(move & 0x02))
                    state["edge_orientations"].append(bool(move & 0x01))
            else:
                moves.append(self._parse_move(high_nibble, low_nibble))

        return state, moves

    def _parse_move(self, face_index: int, turn_index: int) -> dict[str, Any]:
        """Parse a move byte into a move dict."""
        if face_index <= 0 or face_index > len(FACES):
            _LOGGER.debug("Skipping invalid move face index: %s", face_index)
            return {"face": "?", "amount": 0, "notation": "?"}
        face = FACES[face_index - 1]
        amount = TURN_AMOUNTS.get(turn_index - 1, 1)
        notation = face

        if amount == 2:
            notation = f"{face}2"
        elif amount == -1:
            notation = f"{face}'"
        elif amount == -2:
            notation = f"{face}2'"

        return {"face": face, "amount": amount, "notation": notation}

    def _map_corner_colors(
        self, colors: list[int], orientation: int, position: int
    ) -> list[int]:
        """Map corner colors based on orientation and position."""
        if orientation != 3:
            if position in {0, 2, 5, 7}:
                orientation = 3 - orientation

        if orientation == 1:
            return [colors[1], colors[2], colors[0]]
        if orientation == 2:
            return [colors[2], colors[0], colors[1]]
        return [colors[0], colors[1], colors[2]]

    def _map_edge_colors(self, colors: list[int], orientation: bool) -> list[int]:
        """Map edge colors based on orientation."""
        if orientation:
            return [colors[1], colors[0]]
        return [colors[0], colors[1]]

    def _build_state(self, state: Dict[str, list[int]]) -> Tuple[str, Dict[str, bool], bool]:
        """Build cube state string and face solved map."""
        faces: list[str | None] = [None] * 54

        for index, position in enumerate(state["corner_positions"]):
            if position <= 0 or position > len(CORNER_COLORS):
                _LOGGER.debug("Skipping invalid corner position: %s", position)
                continue
            if index >= len(state["corner_orientations"]):
                _LOGGER.debug("Missing corner orientation for index: %s", index)
                continue
            mapped_colors = self._map_corner_colors(
                CORNER_COLORS[position - 1],
                state["corner_orientations"][index],
                index,
            )
            for face_index, cube_index in enumerate(CORNER_FACE_INDICES[index]):
                if face_index >= len(mapped_colors):
                    continue
                color_name = COLORS[mapped_colors[face_index]]
                faces[cube_index] = COLOR_FACE_MAPPING[color_name]

        for index, position in enumerate(state["edge_positions"]):
            if position <= 0 or position > len(EDGE_COLORS):
                _LOGGER.debug("Skipping invalid edge position: %s", position)
                continue
            if index >= len(state["edge_orientations"]):
                _LOGGER.debug("Missing edge orientation for index: %s", index)
                continue
            mapped_colors = self._map_edge_colors(
                EDGE_COLORS[position - 1],
                state["edge_orientations"][index],
            )
            for face_index, cube_index in enumerate(EDGE_FACE_INDICES[index]):
                if face_index >= len(mapped_colors):
                    continue
                color_name = COLORS[mapped_colors[face_index]]
                faces[cube_index] = COLOR_FACE_MAPPING[color_name]

        faces[4] = "U"
        faces[13] = "R"
        faces[22] = "F"
        faces[31] = "D"
        faces[40] = "L"
        faces[49] = "B"

        state_string = "".join(face if face is not None else "?" for face in faces)

        face_states: Dict[str, bool] = {}
        for color_name, face_letter in COLOR_FACE_MAPPING.items():
            tiles = FACE_TILE_INDICES[face_letter]
            face_states[color_name.capitalize()] = all(
                faces[index] == face_letter for index in tiles
            )

        is_solved = all(face_states.values()) if face_states else False
        return state_string, face_states, is_solved


class GiikerConnection(BaseCubeConnection):
    """Manager for Giiker Bluetooth connection."""

    cube_type = "giiker"
    manufacturer = "Giiker"
    model = "Giiker"
    supports_battery = True

    def __init__(self) -> None:
        """Initialize the connection manager."""
        super().__init__()
        self._client: Optional[BleakClient] = None
        self._device: Optional[BLEDevice] = None
        self._data_parser = GiikerDataParser(self._data)
        self._battery_event: asyncio.Event | None = None
        self._notifications_enabled = False
        self._battery_poll_task: asyncio.Task | None = None
        self._battery_poll_interval: float | None = None
        self._battery_idle_timeout: float | None = None

    @property
    def data(self):
        """Return the latest parsed data."""
        return self._data_parser.data

    @property
    def notifications_enabled(self) -> bool:
        """Return whether notifications are enabled."""
        return self._notifications_enabled

    async def connect(self, address: str, device: BLEDevice | None = None) -> None:
        """Connect to the Giiker cube."""
        async with self._connection_lock:
            await self._cleanup_connection()
            target = device
            if target and target.address.lower() != address.lower():
                target = None
            if target is None:
                raise BleakError("Giiker device not available")

            self._device = target
            _LOGGER.info("Attempting to connect to Giiker...")
            try:
                self._client = await establish_connection(
                    BleakClient,
                    target,
                    "Giiker",
                    disconnected_callback=self._handle_disconnect,
                    timeout=CONNECT_TIMEOUT,
                )
            except Exception as err:
                _LOGGER.warning("Giiker establish_connection failed: %s", err)
                raise
            self._is_connected = True
            await self._client.start_notify(
                CHARACTERISTIC_UUID,
                self._cube_notification_handler,
            )
            self._notifications_enabled = True

            try:
                await self._client.start_notify(
                    SYSTEM_READ_UUID,
                    self._system_notification_handler,
                )
            except Exception as err:
                _LOGGER.debug("System notifications not enabled: %s", err)

            try:
                raw_state = await self._client.read_gatt_char(CHARACTERISTIC_UUID)
                self._data_parser.parse_cube_value(raw_state)
                self._last_activity = time.time()
            except Exception as err:
                _LOGGER.debug("Failed to read initial state: %s", err)

            self._notify_state_change()

    async def _cleanup_connection(self) -> None:
        """Clean up any existing connection."""
        await self.stop_battery_polling()
        if self._client is not None:
            try:
                try:
                    await self._client.stop_notify(CHARACTERISTIC_UUID)
                except Exception:
                    pass
                try:
                    await self._client.stop_notify(SYSTEM_READ_UUID)
                except Exception:
                    pass
                await self._client.disconnect()
            except Exception as err:
                _LOGGER.debug("Error during connection cleanup: %s", err)
            finally:
                self._client = None
                self._device = None
                self._is_connected = False
                self._notifications_enabled = False
                self._notify_state_change()

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client:
            await self._client.disconnect()
        await self._cleanup_connection()

    async def enable_notifications(self) -> None:
        """Enable cube notifications."""
        if not self._client or not self._client.is_connected:
            return
        await self._client.start_notify(CHARACTERISTIC_UUID, self._cube_notification_handler)
        self._notifications_enabled = True

    async def disable_notifications(self) -> None:
        """Disable cube notifications."""
        if not self._client or not self._client.is_connected:
            return
        await self._client.stop_notify(CHARACTERISTIC_UUID)
        self._notifications_enabled = False

    @property
    def available(self) -> bool:
        """Return whether the connection is available."""
        return (
            self._is_connected
            and self._client is not None
            and self._client.is_connected
        )

    async def request_battery(self) -> Optional[int]:
        """Request battery level from the cube."""
        if not self._client or not self._client.is_connected:
            return None
        self._battery_event = asyncio.Event()
        try:
            await self._client.write_gatt_char(SYSTEM_WRITE_UUID, bytearray([0xB5]))
        except Exception as err:
            _LOGGER.debug("Failed to request battery: %s", err)
            return None

        try:
            await asyncio.wait_for(self._battery_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            _LOGGER.debug("Battery request timed out")
            return None
        return self._data_parser.data.battery_level

    async def start_battery_polling(
        self,
        interval: float,
        idle_timeout: float | None = None,
    ) -> None:
        """Start background battery polling with optional idle suppression."""
        await self.stop_battery_polling()
        self._battery_poll_interval = interval
        self._battery_idle_timeout = idle_timeout

        async def _poll_loop() -> None:
            while True:
                await asyncio.sleep(interval)
                if not self._client or not self._client.is_connected:
                    continue
                if idle_timeout is not None and self._last_activity is not None:
                    idle_for = time.time() - self._last_activity
                    if idle_for >= idle_timeout:
                        continue
                await self.request_battery()

        self._battery_poll_task = asyncio.create_task(_poll_loop())

    async def stop_battery_polling(self) -> None:
        """Stop battery polling task if running."""
        if self._battery_poll_task is None:
            return
        self._battery_poll_task.cancel()
        self._battery_poll_task = None
        self._battery_poll_interval = None
        self._battery_idle_timeout = None

    def _cube_notification_handler(self, sender: int, data: bytearray) -> None:
        """Handle notifications from the cube characteristic."""
        try:
            last_move = self._data_parser.parse_cube_value(bytes(data))
            self._touch_activity()
            if last_move:
                self._notify_movement(last_move)
            self._notify_state_change()
        except Exception as err:
            _LOGGER.error("Error handling cube notification: %s", err)

    def _system_notification_handler(self, sender: int, data: bytearray) -> None:
        """Handle notifications from the system read characteristic."""
        try:
            self._data_parser.parse_battery_value(bytes(data))
            if self._battery_event is not None:
                self._battery_event.set()
            self._notify_state_change()
        except Exception as err:
            _LOGGER.debug("Error handling system notification: %s", err)

    def _notify_state_change(self) -> None:
        """Notify all state callbacks."""
        try:
            super()._notify_state_change()
        except Exception as err:
            _LOGGER.error("Error in state callback: %s", err)

    def _handle_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection event."""
        self._is_connected = False
        self._notify_state_change()
        _LOGGER.debug("Device disconnected")
