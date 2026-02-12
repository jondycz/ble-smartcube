"""Registry of supported cube models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple, Type

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .base import BaseCubeConnection
from .cubes.giiker import GiikerConnection
from .cubes.gancube import GanConnection
from .cubes.gocube import GoCubeConnection
from .cubes.qiyicube import QiYiConnection


@dataclass(frozen=True)
class CubeModel:
    """Definition of a cube model."""

    cube_type: str
    manufacturer: str
    model: str
    name_prefixes: Tuple[str, ...]
    service_uuids: Tuple[str, ...]
    connection_class: Type[BaseCubeConnection]


CUBE_MODELS: Tuple[CubeModel, ...] = (
    CubeModel(
        cube_type="giiker",
        manufacturer="Giiker",
        model="Giiker",
        name_prefixes=("Gi", "Hi-", "HiG", "Hi-G"),
        service_uuids=(
            "0000aadb-0000-1000-8000-00805f9b34fb",
            "0000aaaa-0000-1000-8000-00805f9b34fb",
        ),
        connection_class=GiikerConnection,
    ),
    CubeModel(
        cube_type="gocube",
        manufacturer="GoCube",
        model="GoCube",
        name_prefixes=("GoCube", "Rubiks"),
        service_uuids=("6e400001-b5a3-f393-e0a9-e50e24dcca9e",),
        connection_class=GoCubeConnection,
    ),
    CubeModel(
        cube_type="gan",
        manufacturer="GAN",
        model="GAN",
        name_prefixes=("GAN", "MG", "AiCube"),
        service_uuids=(
            "0000fff0-0000-1000-8000-00805f9b34fb",
            "6e400001-b5a3-f393-e0a9-e50e24dc4179",
            "8653000a-43e6-47b7-9cb0-5fc21d4ae340",
            "00000010-0000-fff7-fff6-fff5fff4fff0",
        ),
        connection_class=GanConnection,
    ),
    CubeModel(
        cube_type="qiyi",
        manufacturer="QiYi",
        model="QiYi",
        name_prefixes=("QY-QYSC", "XMD-TornadoV4-i"),
        service_uuids=("0000fff0-0000-1000-8000-00805f9b34fb",),
        connection_class=QiYiConnection,
    ),
)


def match_advertisement(
    name: str | None,
    service_uuids: Iterable[str] | None,
) -> Optional[CubeModel]:
    """Match a BLE advertisement to a supported cube model."""
    name_value = name or ""
    uuid_values = tuple(service_uuids or ())

    for model in CUBE_MODELS:
        if name_value.startswith(model.name_prefixes):
            return model
        if any(
            uuid.lower() == suuid.lower()
            for uuid in model.service_uuids
            for suuid in uuid_values
        ):
            return model
    return None


def match_cube_model(discovery_info: BluetoothServiceInfoBleak) -> Optional[CubeModel]:
    """Match a discovery info to a supported cube model."""
    name = discovery_info.name or discovery_info.advertisement.local_name or ""
    service_uuids = discovery_info.advertisement.service_uuids or []
    return match_advertisement(name, service_uuids)


def get_cube_model(cube_type: str) -> CubeModel:
    """Get the cube model definition by type."""
    for model in CUBE_MODELS:
        if model.cube_type == cube_type:
            return model
    return CUBE_MODELS[0]


def create_connection(cube_type: str) -> BaseCubeConnection:
    """Create a connection instance for the given cube type."""
    model = get_cube_model(cube_type)
    return model.connection_class()
