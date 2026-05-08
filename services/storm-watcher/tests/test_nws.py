from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from storm_watcher.nws import fetch_active_alerts, normalize_alert
from stormlead_core import StormSeverity


def _feature(event: str, geometry: dict | None = None) -> dict:
    return {
        "properties": {
            "id": f"urn:test:{event}",
            "event": event,
            "headline": "Storm warning headline",
            "areaDesc": "FL; GA",
            "sent": "2026-05-04T12:00:00Z",
        },
        "geometry": geometry,
    }


def test_normalize_alert_warning() -> None:
    storm = normalize_alert(_feature("Hurricane Warning"))
    assert storm is not None
    assert storm.severity == StormSeverity.WARNING
    assert storm.source == "nws"


def test_normalize_alert_watch() -> None:
    storm = normalize_alert(_feature("Tropical Storm Watch"))
    assert storm is not None
    assert storm.severity == StormSeverity.WATCH


def test_normalize_alert_missing_geometry_does_not_raise() -> None:
    storm = normalize_alert(_feature("Tornado Warning", geometry=None))
    assert storm is not None
    assert storm.bbox_wkt is None


@pytest.mark.asyncio
async def test_fetch_active_alerts_uses_mocked_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NWS_USER_AGENT", "stormlead-test")
    response = MagicMock()
    response.json.return_value = {"features": [_feature("Hurricane Warning")]}
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    with patch("storm_watcher.nws.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        features = await fetch_active_alerts()
    assert len(features) == 1
