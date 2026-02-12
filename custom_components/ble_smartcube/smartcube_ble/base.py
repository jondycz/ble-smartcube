"""Base connection and callback helpers for cube integrations."""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Set

from .models import CubeData


class BaseCubeConnection:
    """Base class for cube connections."""

    cube_type: str = "generic"
    manufacturer: str = ""
    model: str = ""
    supports_battery: bool = False
    supports_state: bool = True

    def __init__(self) -> None:
        self._data = CubeData()
        self._state_callbacks: Set[Callable[[], None]] = set()
        self._movement_callbacks: Set[Callable[[str], None]] = set()
        self._is_connected = False
        self._connection_lock = asyncio.Lock()
        self._last_activity: float | None = None

    @property
    def data(self) -> CubeData:
        """Return the latest parsed data."""
        return self._data

    @property
    def is_connected(self) -> bool:
        """Return whether the cube is connected."""
        return self._is_connected

    @property
    def available(self) -> bool:
        """Return whether the cube is available."""
        return self._is_connected

    def register_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for state changes."""

        def unsubscribe() -> None:
            if callback in self._state_callbacks:
                self._state_callbacks.remove(callback)

        self._state_callbacks.add(callback)
        return unsubscribe

    def add_movement_callback(self, callback: Callable[[str], None]) -> None:
        """Add a callback for movement events."""
        self._movement_callbacks.add(callback)

    def remove_movement_callback(self, callback: Callable[[str], None]) -> None:
        """Remove a callback for movement events."""
        self._movement_callbacks.discard(callback)

    def _notify_state_change(self) -> None:
        """Notify all state callbacks."""
        for callback in self._state_callbacks:
            callback()

    def _notify_movement(self, movement: str) -> None:
        """Notify all movement callbacks."""
        for callback in self._movement_callbacks:
            callback(movement)

    def _touch_activity(self) -> None:
        """Record the last activity time."""
        self._last_activity = time.time()

    async def request_battery(self) -> int | None:
        """Request battery level from the cube if supported."""
        return self._data.battery_level
