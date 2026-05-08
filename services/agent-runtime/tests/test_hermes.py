from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_runtime.hermes import _fetch_weekly_traces, _persist_proposals, _summarize_traces


def test_summarize_traces_empty_digest() -> None:
    assert "Traces analyzed: 0" in _summarize_traces([])


def test_summarize_traces_counts_failures() -> None:
    summary = _summarize_traces([{"status": "error"}, {"level": "DEFAULT"}])
    assert "Traces analyzed: 2" in summary
    assert "Failure-like traces: 1" in summary


@pytest.mark.asyncio
async def test_fetch_weekly_traces_connection_error_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse.local")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret")
    client = MagicMock()
    client.get = AsyncMock(side_effect=Exception("connection refused"))
    with patch("agent_runtime.hermes.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        assert await _fetch_weekly_traces() == []


@pytest.mark.asyncio
async def test_persist_proposals_empty_list_returns_zero() -> None:
    assert await _persist_proposals([], date.today()) == 0
