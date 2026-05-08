from __future__ import annotations

from unittest.mock import patch

import pytest
from storm_watcher.tropycal_poller import fetch_active_tropical_systems, normalize_tropical_storm
from stormlead_core import StormSeverity


def test_normalize_tropical_storm_valid_dict() -> None:
    storm = normalize_tropical_storm(
        {
            "operational_id": "AL012026",
            "name": "Ana",
            "lat": [25.0],
            "lon": [-80.0],
            "last_update": "2026-08-01T12:00:00Z",
        }
    )
    assert storm is not None
    assert storm.external_id == "AL012026"
    assert storm.severity == StormSeverity.WARNING
    assert storm.raw["latest_position"] == {"lat": 25.0, "lon": -80.0}


def test_normalize_tropical_storm_empty_dict_returns_none() -> None:
    assert normalize_tropical_storm({}) is None


def test_normalize_tropical_storm_inactive_returns_none() -> None:
    assert normalize_tropical_storm({"name": "Archive Storm", "operational_id": None}) is None


@pytest.mark.asyncio
async def test_fetch_active_tropical_systems_uses_mocked_loader() -> None:
    with patch(
        "storm_watcher.tropycal_poller._load_basin_active_systems",
        side_effect=lambda basin: [{"operational_id": basin, "name": basin}],
    ):
        systems = await fetch_active_tropical_systems()
    assert {system["operational_id"] for system in systems} == {"north_atlantic", "east_pacific"}
