from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from agent_runtime.nurture import _send_nurture_outreach, nurture_lead


class _Context:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def workflow_input(self) -> dict:
        return self._payload


def test_nurture_accepts_unsold_payload_shape() -> None:
    lead_id = uuid4()
    context = _Context({"lead_id": str(lead_id), "source_event": "lead.unsold"})
    assert callable(nurture_lead)
    assert context.workflow_input()["lead_id"] == str(lead_id)
    assert context.workflow_input()["source_event"] == "lead.unsold"


class _Lead:
    id = uuid4()
    name = "Synthetic Lead"
    phone_e164 = "+13215550001"
    email = "lead@example.test"
    city = "Orlando"
    state = "FL"
    requested_service = "tree_removal"
    damage_description = "x" * 600


@pytest.mark.asyncio
async def test_send_nurture_outreach_empty_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NURTURE_WEBHOOK_URL", raising=False)
    result = await _send_nurture_outreach(cast(Any, _Lead()))
    assert result == {"sent": False, "reason": "NURTURE_WEBHOOK_URL not set"}


@pytest.mark.asyncio
async def test_send_nurture_outreach_posts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NURTURE_WEBHOOK_URL", "http://localhost:9998/nurture")
    response = MagicMock(status_code=204)
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    with patch("agent_runtime.nurture.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        result = await _send_nurture_outreach(cast(Any, _Lead()))
    assert result == {"sent": True, "status_code": 204}
    posted = client.post.await_args.kwargs["json"]
    assert len(posted["damage_description"]) == 500


@pytest.mark.asyncio
async def test_send_nurture_outreach_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NURTURE_WEBHOOK_URL", "http://localhost:9998/nurture")
    request = httpx.Request("POST", "http://localhost:9998/nurture")
    response = httpx.Response(503, request=request)
    error = httpx.HTTPStatusError("server error", request=request, response=response)
    mocked_response = MagicMock(status_code=503)
    mocked_response.raise_for_status.side_effect = error
    client = MagicMock()
    client.post = AsyncMock(return_value=mocked_response)
    with patch("agent_runtime.nurture.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        result = await _send_nurture_outreach(cast(Any, _Lead()))
    assert result == {"sent": False, "reason": "http_503"}
