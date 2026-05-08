from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from enrich_worker.geocode import geocode_address


@pytest.mark.asyncio
async def test_geocode_empty_address_returns_none() -> None:
    assert await geocode_address("", "", "", "") is None


@pytest.mark.asyncio
async def test_geocode_empty_result_returns_none() -> None:
    response = MagicMock()
    response.json.return_value = []
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    with patch("enrich_worker.geocode.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        assert await geocode_address("1 Main", "Orlando", "FL", "32801") is None


@pytest.mark.asyncio
async def test_geocode_success() -> None:
    response = MagicMock()
    response.json.return_value = [{"lat": "28.5", "lon": "-81.4", "display_name": "Orlando"}]
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    with patch("enrich_worker.geocode.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        point = await geocode_address("1 Main", "Orlando", "FL", "32801")
    assert point is not None
    assert point.lat == 28.5
    assert point.lon == -81.4
