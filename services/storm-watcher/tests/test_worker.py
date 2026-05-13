from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from storm_watcher import worker
from stormlead_core import Storm, StormSeverity


def _nws_feature(event: str) -> dict[str, Any]:
    return {
        "properties": {
            "id": f"urn:local:{event}",
            "event": event,
            "headline": "Local synthetic storm alert",
            "areaDesc": "FL; GA",
            "sent": "2026-08-01T12:00:00Z",
        },
        "geometry": None,
    }


def _synthetic_storm_with_impacted_zips() -> Storm:
    return Storm(
        external_id="urn:local:storm-zips",
        name="Local ZIP Proof Storm",
        source="local",
        severity=StormSeverity.WARNING,
        affected_states=["FL"],
        affected_counties=["12095"],
        detected_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        raw={"impacted_zips": ["32801", "32801-9999", "invalid", 32803]},
    )


class _FakeStormRawResult:
    def __init__(self, raw: dict[str, Any] | None) -> None:
        self.raw = raw

    def scalar_one_or_none(self) -> dict[str, Any] | None:
        return self.raw


class _FakeStormSession:
    def __init__(self, raw: dict[str, Any] | None) -> None:
        self.raw = raw

    async def __aenter__(self) -> _FakeStormSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _stmt: object) -> _FakeStormRawResult:
        return _FakeStormRawResult(self.raw)


@pytest.mark.asyncio
async def test_poll_nws_uses_synthetic_fetch_and_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upserted: list[str] = []

    async def fake_fetch_active_alerts() -> list[dict[str, Any]]:
        return [_nws_feature("Hurricane Warning"), _nws_feature("Dense Fog Advisory")]

    async def fake_upsert_storm(storm: Any) -> bool:
        upserted.append(storm.external_id)
        return True

    monkeypatch.setattr(worker, "fetch_active_alerts", fake_fetch_active_alerts)
    monkeypatch.setattr(worker, "_upsert_storm", fake_upsert_storm)

    result = await worker._poll_nws()

    assert result == {"total": 2, "new": 1}
    assert upserted == ["urn:local:Hurricane Warning"]


def test_storm_row_values_preserve_impacted_zips_for_local_geo_targeting() -> None:
    storm = _synthetic_storm_with_impacted_zips()

    values = worker._storm_row_values(storm)

    assert values["external_id"] == "urn:local:storm-zips"
    assert values["raw"] == storm.raw
    assert worker.impacted_zips_from_storm_raw(values["raw"]) == ["32801", "32803"]


@pytest.mark.asyncio
async def test_list_impacted_zips_for_storm_reads_persisted_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storm = _synthetic_storm_with_impacted_zips()
    monkeypatch.setattr(worker, "get_session", lambda: _FakeStormSession(storm.raw))

    zips = await worker.list_impacted_zips_for_storm(storm.external_id)

    assert zips == ["32801", "32803"]


@pytest.mark.asyncio
async def test_poll_fema_uses_synthetic_fetch_and_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upserted: list[str] = []

    async def fake_fetch_recent_declarations(days_back: int = 14) -> list[dict[str, Any]]:
        assert days_back == 14
        return [
            {
                "disasterNumber": "1234",
                "state": "FL",
                "incidentType": "Hurricane",
                "declarationTitle": "Hurricane Local Test",
                "declarationDate": "2026-08-01T12:00:00Z",
                "placeCode": "001",
            },
            {
                "disasterNumber": "9999",
                "state": "FL",
                "incidentType": "Earthquake",
                "declarationTitle": "Ignored Event",
                "declarationDate": "2026-08-01T12:00:00Z",
            },
        ]

    async def fake_upsert_storm(storm: Any) -> bool:
        upserted.append(storm.external_id)
        return True

    monkeypatch.setattr(worker, "fetch_recent_declarations", fake_fetch_recent_declarations)
    monkeypatch.setattr(worker, "_upsert_storm", fake_upsert_storm)

    result = await worker._poll_fema()

    assert result == {"total": 2, "new": 1}
    assert upserted == ["DR-1234-FL"]


@pytest.mark.asyncio
async def test_poll_nhc_tropycal_uses_synthetic_fetch_in_hurricane_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upserted: list[str] = []

    async def fake_fetch_active_tropical_systems() -> list[dict[str, Any]]:
        return [
            {
                "operational_id": "AL012026",
                "name": "Ana",
                "lat": [25.0],
                "lon": [-80.0],
                "last_update": "2026-08-01T12:00:00Z",
            },
            {},
        ]

    async def fake_upsert_storm(storm: Any) -> bool:
        upserted.append(storm.external_id)
        return True

    monkeypatch.setattr(worker, "_is_hurricane_season", lambda: True)
    monkeypatch.setattr(worker, "fetch_active_tropical_systems", fake_fetch_active_tropical_systems)
    monkeypatch.setattr(worker, "_upsert_storm", fake_upsert_storm)

    result = await worker._poll_nhc_tropycal()

    assert result == {"total": 2, "new": 1}
    assert upserted == ["AL012026"]


@pytest.mark.asyncio
async def test_poll_nhc_tropycal_skips_outside_hurricane_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_fetch() -> list[dict[str, Any]]:
        raise AssertionError("outside-season poll should not fetch NHC data")

    monkeypatch.setattr(worker, "_is_hurricane_season", lambda: False)
    monkeypatch.setattr(worker, "fetch_active_tropical_systems", unexpected_fetch)

    assert await worker._poll_nhc_tropycal() == {
        "skipped": True,
        "reason": "outside_hurricane_season",
    }
