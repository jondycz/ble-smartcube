"""Helpers for building cube state and solved face data."""

from __future__ import annotations

import time
from typing import Dict, Tuple

from ..models import CubeData

COLOR_FACE_MAPPING = {
    "blue": "B",
    "yellow": "D",
    "orange": "L",
    "white": "U",
    "red": "R",
    "green": "F",
}

FACE_TILE_INDICES = {
    "U": list(range(0, 9)),
    "R": list(range(9, 18)),
    "F": list(range(18, 27)),
    "D": list(range(27, 36)),
    "L": list(range(36, 45)),
    "B": list(range(45, 54)),
}


def build_face_states(state_string: str) -> Tuple[Dict[str, bool], bool]:
    """Return face solved map and solved flag from a state string."""
    if not state_string or len(state_string) < 54:
        return {}, False

    faces = list(state_string)
    face_states: Dict[str, bool] = {}
    for color_name, face_letter in COLOR_FACE_MAPPING.items():
        tiles = FACE_TILE_INDICES[face_letter]
        face_states[color_name.capitalize()] = all(
            faces[index] == face_letter for index in tiles
        )

    is_solved = all(face_states.values()) if face_states else False
    return face_states, is_solved


def update_cube_state(data: CubeData, state_string: str) -> None:
    """Update data fields from a state string."""
    data.state_string = state_string
    face_states, is_solved = build_face_states(state_string)
    data.face_states = face_states
    data.is_solved = is_solved
    data.last_update = time.time()
