from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from agent_runtime.nurture import (
    _channel_suppression_states,
    _local_communication_outbox,
    _outbox_channels,
    _send_nurture_outreach,
    nurture_lead,
)
from stormlead_core import LeadStatus, PipelineState


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


class _ScalarResult:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        return self._values


@pytest.mark.asyncio
async def test_send_nurture_outreach_empty_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NURTURE_WEBHOOK_URL", raising=False)
    result = await _send_nurture_outreach(cast(Any, _Lead()))
    assert result["sent"] is False
    assert result["reason"] == "local_outbox_pending"
    assert result["would_contact_provider"] is False
    assert {entry["channel"] for entry in result["outbox"]} == {
        "sms",
        "email",
        "voice",
        "nurture_webhook",
    }
    sms_entry = next(entry for entry in result["outbox"] if entry["channel"] == "sms")
    assert sms_entry["status"] == "blocked_provider_approval"
    assert sms_entry["provider_gate"]["area"] == "sms"
    assert sms_entry["recipient"] == {"phone_e164_present": True, "email_present": False}
    assert _Lead.phone_e164 not in str(result["outbox"])
    assert _Lead.email not in str(result["outbox"])


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
    assert result["sent"] is True
    assert result["status_code"] == 204
    assert result["would_contact_provider"] is False
    webhook_entry = next(
        entry for entry in result["outbox"] if entry["channel"] == "nurture_webhook"
    )
    assert webhook_entry["status"] == "local_dispatch_allowed"
    posted = client.post.await_args.kwargs["json"]
    assert len(posted["damage_description"]) == 500


@pytest.mark.asyncio
async def test_send_nurture_outreach_rejects_external_without_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NURTURE_WEBHOOK_URL", "https://hooks.example.com/nurture")
    monkeypatch.delenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", raising=False)
    monkeypatch.delenv("STORMLEAD_APPROVED_NURTURE_WEBHOOK_HOSTS", raising=False)

    with patch("agent_runtime.nurture.httpx.AsyncClient") as async_client:
        result = await _send_nurture_outreach(cast(Any, _Lead()))

    assert result["sent"] is False
    assert result["reason"] == "nurture webhook_url is not locally safe or approved"
    assert result["would_contact_provider"] is False
    webhook_entry = next(
        entry for entry in result["outbox"] if entry["channel"] == "nurture_webhook"
    )
    assert webhook_entry["status"] == "blocked_provider_approval"
    async_client.assert_not_called()


@pytest.mark.asyncio
async def test_send_nurture_outreach_queues_approved_external_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NURTURE_WEBHOOK_URL", "https://hooks.example.com/nurture")
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.setenv("STORMLEAD_APPROVED_NURTURE_WEBHOOK_HOSTS", "hooks.example.com")
    monkeypatch.setattr(
        "stormlead_core.env_gate.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    with patch("agent_runtime.nurture.httpx.AsyncClient") as async_client:
        result = await _send_nurture_outreach(cast(Any, _Lead()))

    assert result["sent"] is False
    assert result["reason"] == "external_nurture_webhook_pending_action_approval"
    assert result["would_contact_provider"] is False
    webhook_entry = next(
        entry for entry in result["outbox"] if entry["channel"] == "nurture_webhook"
    )
    assert webhook_entry["status"] == "provider_approved_pending_dispatch"
    async_client.assert_not_called()


@pytest.mark.asyncio
async def test_send_nurture_outreach_rejects_approved_external_private_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NURTURE_WEBHOOK_URL", "https://hooks.example.com/nurture")
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.setenv("STORMLEAD_APPROVED_NURTURE_WEBHOOK_HOSTS", "hooks.example.com")
    monkeypatch.setattr(
        "stormlead_core.env_gate.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("10.0.0.5", 443))],
    )

    with patch("agent_runtime.nurture.httpx.AsyncClient") as async_client:
        result = await _send_nurture_outreach(cast(Any, _Lead()))

    assert result["sent"] is False
    assert result["reason"] == "nurture webhook_url is not locally safe or approved"
    assert result["would_contact_provider"] is False
    webhook_entry = next(
        entry for entry in result["outbox"] if entry["channel"] == "nurture_webhook"
    )
    assert webhook_entry["status"] == "blocked_provider_approval"
    async_client.assert_not_called()


def test_local_communication_outbox_skips_missing_contacts() -> None:
    lead = MagicMock(phone_e164=None, email=None)

    outbox = _local_communication_outbox(lead, webhook_url="", source_event="lead.rejected")

    sms_entry = next(entry for entry in outbox if entry["channel"] == "sms")
    email_entry = next(entry for entry in outbox if entry["channel"] == "email")
    voice_entry = next(entry for entry in outbox if entry["channel"] == "voice")
    webhook_entry = next(entry for entry in outbox if entry["channel"] == "nurture_webhook")
    assert sms_entry["status"] == "skipped_missing_contact"
    assert email_entry["status"] == "skipped_missing_contact"
    assert voice_entry["status"] == "skipped_missing_contact"
    assert webhook_entry["status"] == "not_configured"
    assert {entry["would_contact_provider"] for entry in outbox} == {False}


def test_local_communication_outbox_marks_channel_suppressions() -> None:
    outbox = _local_communication_outbox(
        cast(Any, _Lead()),
        webhook_url="",
        source_event="lead.unsold",
        channel_suppressions={"sms": True, "email": False, "voice": True},
    )

    sms_entry = next(entry for entry in outbox if entry["channel"] == "sms")
    email_entry = next(entry for entry in outbox if entry["channel"] == "email")
    voice_entry = next(entry for entry in outbox if entry["channel"] == "voice")
    assert sms_entry["status"] == "suppressed_opt_out"
    assert sms_entry["requires_action_approval"] is False
    assert email_entry["status"] == "blocked_provider_approval"
    assert voice_entry["status"] == "suppressed_opt_out"
    assert _outbox_channels({"outbox": outbox}) == ["email", "nurture_webhook"]


@pytest.mark.asyncio
async def test_channel_suppression_states_match_contact_by_channel() -> None:
    lead = MagicMock(phone_e164="+13215550001", email="LEAD@EXAMPLE.TEST")

    class Session:
        async def scalars(self, statement: object) -> _ScalarResult:
            self.statement = str(statement)
            return _ScalarResult(["sms", "email"])

    session = Session()
    result = await _channel_suppression_states(session, cast(Any, lead))

    assert result == {"sms": True, "email": True, "voice": False}
    assert "channel_suppressions" in session.statement


@pytest.mark.asyncio
async def test_send_nurture_outreach_blocks_webhook_when_channel_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NURTURE_WEBHOOK_URL", "http://localhost:9998/nurture")

    with patch("agent_runtime.nurture.httpx.AsyncClient") as async_client:
        result = await _send_nurture_outreach(
            cast(Any, _Lead()),
            channel_suppressions={"sms": True, "email": False, "voice": False},
        )

    assert result["sent"] is False
    assert result["reason"] == "channel_suppression_pending"
    assert result["would_contact_provider"] is False
    sms_entry = next(entry for entry in result["outbox"] if entry["channel"] == "sms")
    webhook_entry = next(
        entry for entry in result["outbox"] if entry["channel"] == "nurture_webhook"
    )
    assert sms_entry["status"] == "suppressed_opt_out"
    assert webhook_entry["status"] == "suppressed_opt_out"
    assert webhook_entry["requires_action_approval"] is False
    async_client.assert_not_called()


@pytest.mark.asyncio
async def test_send_nurture_outreach_skips_webhook_dns_when_channel_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NURTURE_WEBHOOK_URL", "https://hooks.example.com/nurture")
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.setenv("STORMLEAD_APPROVED_NURTURE_WEBHOOK_HOSTS", "hooks.example.com")
    getaddrinfo = MagicMock()
    monkeypatch.setattr("stormlead_core.env_gate.socket.getaddrinfo", getaddrinfo)

    result = await _send_nurture_outreach(
        cast(Any, _Lead()),
        channel_suppressions={"sms": True, "email": False, "voice": False},
    )

    assert result["sent"] is False
    assert result["reason"] == "channel_suppression_pending"
    getaddrinfo.assert_not_called()


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
    assert result["sent"] is False
    assert result["reason"] == "http_503"
    assert result["would_contact_provider"] is False
    assert {entry["channel"] for entry in result["outbox"]} == {
        "sms",
        "email",
        "voice",
        "nurture_webhook",
    }


@pytest.mark.asyncio
async def test_nurture_lead_does_not_mark_nurtured_when_outreach_fails() -> None:
    lead_id = uuid4()
    row = MagicMock(id=lead_id, phone_e164=None, email=None)
    row.status = LeadStatus.UNSOLD.value

    class SessionContext:
        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *_args: object) -> object:
            return row

    record_transition = AsyncMock()
    with (
        patch("agent_runtime.nurture.get_session", return_value=SessionContext()),
        patch(
            "agent_runtime.nurture._send_nurture_outreach",
            new=AsyncMock(return_value={"sent": False, "reason": "NURTURE_WEBHOOK_URL not set"}),
        ),
        patch("agent_runtime.nurture.record_transition", new=record_transition),
        patch("agent_runtime.nurture.emit_event"),
        patch("agent_runtime.nurture.emit_metric"),
    ):
        result = await nurture_lead(cast(Any, _Context({"lead_id": str(lead_id)})))

    assert row.status == LeadStatus.NURTURE_FAILED.value
    assert result["status"] == LeadStatus.NURTURE_FAILED.value
    assert not result["external_contact_made"]
    assert record_transition.await_args is not None
    assert record_transition.await_args.kwargs["to_state"] == PipelineState.NURTURE_FAILED


@pytest.mark.asyncio
async def test_nurture_lead_records_redacted_outbox_without_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NURTURE_WEBHOOK_URL", raising=False)
    lead_id = uuid4()
    row = MagicMock()
    row.id = lead_id
    row.name = "Jane Homeowner"
    row.phone_e164 = "+13215550001"
    row.email = "lead@example.test"
    row.city = "Orlando"
    row.state = "FL"
    row.requested_service = "tree_removal"
    row.damage_description = "private storm damage notes"
    row.status = LeadStatus.UNSOLD.value

    class SessionContext:
        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *_args: object) -> object:
            return row

        async def scalar(self, *_args: object) -> object:
            return None

        async def scalars(self, *_args: object) -> _ScalarResult:
            return _ScalarResult([])

    record_transition = AsyncMock()
    with (
        patch("agent_runtime.nurture.get_session", return_value=SessionContext()),
        patch("agent_runtime.nurture.record_transition", new=record_transition),
        patch("agent_runtime.nurture.emit_event"),
        patch("agent_runtime.nurture.emit_metric"),
    ):
        result = await nurture_lead(cast(Any, _Context({"lead_id": str(lead_id)})))

    assert result["external_contact_made"] is False
    assert result["outreach"]["reason"] == "local_outbox_pending"
    assert record_transition.await_args is not None
    transition_payload = record_transition.await_args.kwargs["payload"]
    assert transition_payload["external_contact_made"] is False
    assert set(transition_payload["outbox_channels"]) == {
        "sms",
        "email",
        "voice",
        "nurture_webhook",
    }
    payload_text = str(transition_payload)
    assert row.name not in payload_text
    assert row.phone_e164 not in payload_text
    assert row.email not in payload_text
    assert row.damage_description not in payload_text


@pytest.mark.asyncio
async def test_nurture_lead_records_redacted_outbox_after_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    webhook_url = "http://localhost:9998/nurture?token=secret-token"
    monkeypatch.setenv("NURTURE_WEBHOOK_URL", webhook_url)
    lead_id = uuid4()
    row = MagicMock()
    row.id = lead_id
    row.name = "Jane Homeowner"
    row.phone_e164 = "+13215550001"
    row.email = "lead@example.test"
    row.city = "Orlando"
    row.state = "FL"
    row.requested_service = "tree_removal"
    row.damage_description = "private storm damage notes"
    row.status = LeadStatus.UNSOLD.value

    class SessionContext:
        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *_args: object) -> object:
            return row

        async def scalar(self, *_args: object) -> object:
            return None

        async def scalars(self, *_args: object) -> _ScalarResult:
            return _ScalarResult([])

    request = httpx.Request("POST", webhook_url)
    response = httpx.Response(503, request=request)
    error = httpx.HTTPStatusError("server error", request=request, response=response)
    mocked_response = MagicMock(status_code=503)
    mocked_response.raise_for_status.side_effect = error
    client = MagicMock()
    client.post = AsyncMock(return_value=mocked_response)
    record_transition = AsyncMock()
    with (
        patch("agent_runtime.nurture.get_session", return_value=SessionContext()),
        patch("agent_runtime.nurture.httpx.AsyncClient") as async_client,
        patch("agent_runtime.nurture.record_transition", new=record_transition),
        patch("agent_runtime.nurture.emit_event"),
        patch("agent_runtime.nurture.emit_metric"),
    ):
        async_client.return_value.__aenter__.return_value = client
        result = await nurture_lead(cast(Any, _Context({"lead_id": str(lead_id)})))

    assert result["status"] == LeadStatus.NURTURE_FAILED.value
    assert record_transition.await_args is not None
    transition_payload = record_transition.await_args.kwargs["payload"]
    assert transition_payload["outreach"]["reason"] == "http_503"
    assert set(transition_payload["outbox_channels"]) == {
        "sms",
        "email",
        "voice",
        "nurture_webhook",
    }
    payload_text = str(transition_payload)
    assert "http://localhost:9998" in payload_text
    assert webhook_url not in payload_text
    assert "secret-token" not in payload_text
    assert "token=" not in payload_text
    assert row.name not in payload_text
    assert row.phone_e164 not in payload_text
    assert row.email not in payload_text
    assert row.damage_description not in payload_text


@pytest.mark.asyncio
async def test_nurture_lead_hides_dispatchable_channels_when_channel_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NURTURE_WEBHOOK_URL", raising=False)
    lead_id = uuid4()
    row = MagicMock()
    row.id = lead_id
    row.name = "Jane Homeowner"
    row.phone_e164 = "+13215550001"
    row.email = "lead@example.test"
    row.city = "Orlando"
    row.state = "FL"
    row.requested_service = "tree_removal"
    row.damage_description = "private storm damage notes"
    row.status = LeadStatus.UNSOLD.value

    class SessionContext:
        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *_args: object) -> object:
            return row

        async def scalar(self, *_args: object) -> object:
            return None

        async def scalars(self, *_args: object) -> _ScalarResult:
            return _ScalarResult(["sms"])

    record_transition = AsyncMock()
    with (
        patch("agent_runtime.nurture.get_session", return_value=SessionContext()),
        patch("agent_runtime.nurture.record_transition", new=record_transition),
        patch("agent_runtime.nurture.emit_event"),
        patch("agent_runtime.nurture.emit_metric"),
    ):
        result = await nurture_lead(cast(Any, _Context({"lead_id": str(lead_id)})))

    assert result["outreach"]["reason"] == "channel_suppression_pending"
    assert record_transition.await_args is not None
    transition_payload = record_transition.await_args.kwargs["payload"]
    assert transition_payload["outbox_channels"] == []
    sms_entry = next(
        entry for entry in transition_payload["outreach"]["outbox"] if entry["channel"] == "sms"
    )
    assert sms_entry["status"] == "suppressed_opt_out"


@pytest.mark.asyncio
async def test_nurture_lead_rechecks_suppression_before_outreach() -> None:
    lead_id = uuid4()
    row = MagicMock(id=lead_id, phone_e164="+13215550001", email="LEAD@EXAMPLE.TEST")
    row.status = LeadStatus.UNSOLD.value

    class SessionContext:
        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *_args: object) -> object:
            return row

        async def scalar(self, *_args: object) -> object:
            return uuid4()

    send_nurture = AsyncMock(return_value={"sent": True})
    record_transition = AsyncMock()
    with (
        patch("agent_runtime.nurture.get_session", return_value=SessionContext()),
        patch("agent_runtime.nurture._send_nurture_outreach", new=send_nurture),
        patch("agent_runtime.nurture.record_transition", new=record_transition),
        patch("agent_runtime.nurture.emit_event"),
        patch("agent_runtime.nurture.emit_metric"),
    ):
        result = await nurture_lead(cast(Any, _Context({"lead_id": str(lead_id)})))

    send_nurture.assert_not_awaited()
    assert row.status == LeadStatus.NURTURE_FAILED.value
    assert not result["external_contact_made"]
    assert result["outreach"] == {"sent": False, "reason": "suppressed_opt_out"}
    assert record_transition.await_args is not None
    transition_payload = record_transition.await_args.kwargs["payload"]
    assert transition_payload["external_contact_made"] is False
    assert transition_payload["outbox_channels"] == []
    assert transition_payload["outreach"]["reason"] == "suppressed_opt_out"
    assert "outbox" not in transition_payload["outreach"]
