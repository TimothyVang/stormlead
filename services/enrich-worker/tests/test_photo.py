from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from enrich_worker.photo import classify_photo


@pytest.mark.asyncio
async def test_classify_photo_empty_bytes_returns_none() -> None:
    assert await classify_photo(b"") is None


@pytest.mark.asyncio
async def test_classify_photo_low_confidence_returns_none() -> None:
    response = MagicMock()
    response.json.return_value = {
        "choices": [
            {"message": {"content": json.dumps({"damage_tier": 1, "confidence": 0.4})}}
        ]
    }
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    with patch("enrich_worker.photo.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        assert await classify_photo(b"fake") is None


@pytest.mark.asyncio
async def test_classify_photo_success() -> None:
    response = MagicMock()
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"damage_tier": 3, "damage_type": "tree", "confidence": 0.91}
                    )
                }
            }
        ]
    }
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    with patch("enrich_worker.photo.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        result = await classify_photo(b"fake")
    assert result is not None
    assert result["damage_tier"] == 3
    assert result["confidence"] == 0.91
