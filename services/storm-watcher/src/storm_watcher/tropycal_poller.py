"""NHC tropical cyclone poller using Tropycal.

Tropycal performs synchronous ATCF/NHC loading, so fetches are isolated in an
executor and each basin is treated as best-effort.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from stormlead_core import Storm, StormSeverity, get_logger

log = get_logger(__name__)

BASINS = ("north_atlantic", "east_pacific")


def _storm_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("operational_id") or value.get("id") or value.get("name"):
            yield value
            return
        for child in value.values():
            yield from _storm_dicts(child)
        return

    if isinstance(value, list | tuple):
        for child in value:
            yield from _storm_dicts(child)


def _dataset_storm_dicts(dataset: Any) -> list[dict[str, Any]]:
    storms: list[dict[str, Any]] = []
    for attr in ("storms", "storm_dict", "data", "tracks"):
        value = getattr(dataset, attr, None)
        if value is not None:
            storms.extend(_storm_dicts(value))
    return storms


def _load_basin_active_systems(basin: str) -> list[dict[str, Any]]:
    from tropycal.tracks import TrackDataset

    dataset = TrackDataset(basin=basin, source="nhc")
    return [storm for storm in _dataset_storm_dicts(dataset) if storm.get("operational_id")]


async def fetch_active_tropical_systems() -> list[dict[str, Any]]:
    """Return currently operational NHC systems from supported basins."""
    loop = asyncio.get_event_loop()
    systems: list[dict[str, Any]] = []
    for basin in BASINS:
        try:
            systems.extend(await loop.run_in_executor(None, _load_basin_active_systems, basin))
        except Exception as exc:  # pragma: no cover - exercised via mocked tests
            log.warning("tropycal.basin_fetch_failed", basin=basin, error=str(exc))
    return systems


def _last_float(value: Any) -> float | None:
    if isinstance(value, list | tuple):
        if not value:
            return None
        return _last_float(value[-1])
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
    return datetime.now(UTC)


def normalize_tropical_storm(storm_dict: dict[str, Any]) -> Storm | None:
    """Convert one active NHC/Tropycal storm dict into a Storm model."""
    if not storm_dict:
        return None

    operational_id = storm_dict.get("operational_id")
    if not operational_id:
        return None

    external_id = str(operational_id)
    name = str(storm_dict.get("name") or storm_dict.get("storm_name") or external_id)
    detected_at = _parse_time(
        storm_dict.get("last_update")
        or storm_dict.get("last_updated")
        or storm_dict.get("date")
        or storm_dict.get("time")
    )

    lat = _last_float(
        storm_dict.get("lat") or storm_dict.get("lats") or storm_dict.get("latitude")
    )
    lon = _last_float(
        storm_dict.get("lon") or storm_dict.get("lons") or storm_dict.get("longitude")
    )
    raw = dict(storm_dict)
    if lat is not None and lon is not None:
        raw.setdefault("latest_position", {"lat": lat, "lon": lon})

    return Storm(
        id=uuid4(),
        external_id=external_id,
        name=name,
        source="nhc",
        severity=StormSeverity.WARNING,
        affected_states=[],
        affected_counties=[],
        detected_at=detected_at,
        raw=raw,
    )
