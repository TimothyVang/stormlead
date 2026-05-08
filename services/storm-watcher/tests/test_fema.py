from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from storm_watcher.fema import fetch_recent_declarations, normalize_declaration
from stormlead_core import StormSeverity


def _declaration(incident_type: str = "Hurricane") -> dict:
    return {
        "disasterNumber": "1234",
        "state": "FL",
        "incidentType": incident_type,
        "declarationTitle": "Hurricane Test",
        "declarationDate": "2026-05-04T12:00:00Z",
        "placeCode": "001",
    }


def test_normalize_declaration_storm_type() -> None:
    storm = normalize_declaration(_declaration())
    assert storm is not None
    assert storm.severity == StormSeverity.DECLARED
    assert storm.external_id == "DR-1234-FL"


def test_normalize_declaration_non_storm_returns_none() -> None:
    assert normalize_declaration(_declaration("Earthquake")) is None


def test_normalize_declaration_county_optional() -> None:
    declaration = _declaration("Tornado")
    declaration.pop("placeCode")
    storm = normalize_declaration(declaration)
    assert storm is not None
    assert storm.affected_counties == []


@pytest.mark.asyncio
async def test_fetch_recent_declarations_uses_mocked_http() -> None:
    response = MagicMock()
    response.json.return_value = {"DisasterDeclarationsSummaries": [_declaration()]}
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    with patch("storm_watcher.fema.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        declarations = await fetch_recent_declarations(days_back=1)
    assert declarations == [_declaration()]
