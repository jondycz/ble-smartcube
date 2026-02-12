"""Data models for cube state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class CubeData:
    """Data class for cube state."""

    battery_level: int | None = None
    is_solved: bool = False
    face_states: Dict[str, bool] | None = None
    last_move: str | None = None
    last_raw: bytes | None = None
    last_decrypted: bytes | None = None
    state_string: str | None = None
    last_update: float | None = None

    def __post_init__(self) -> None:
        """Initialize face states dictionary."""
        if self.face_states is None:
            self.face_states = {}
