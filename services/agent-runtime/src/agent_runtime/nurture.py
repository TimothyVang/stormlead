from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from hatchet_sdk import Context
from sqlalchemy import and_, or_, select
from stormlead_core import (
    LeadStatus,
    PipelineState,
    ProviderArea,
    ProviderDecision,
    bind_correlation_id,
    emit_event,
    emit_metric,
    get_logger,
    provider_decision,
)
from stormlead_db import (
    ChannelSuppression,
    LeadRow,
    SuppressionEntry,
    get_session,
    record_transition,
)

log = get_logger(__name__)
LOCAL_OUTBOX_TEMPLATE = "stormlead_nurture_followup_v1"
EMERGENCY_SAFETY_MESSAGE = (
    "For injuries, power lines, active danger, unstable structures, or blocked emergency access, "
    "stay away from the damage area and contact emergency services or the utility before "
    "contractor matching."
)
SAFETY_MESSAGE_FLAGS = frozenset(
    {"power_line", "injury", "active_danger", "roof_impact", "structure_impact", "emergency"}
)
PROVIDER_CHANNELS: tuple[tuple[str, ProviderArea], ...] = (
    ("sms", ProviderArea.SMS),
    ("email", ProviderArea.EMAIL),
    ("voice", ProviderArea.VOICE),
)


def _nurture_webhook_allowed(value: str) -> bool:
    return provider_decision(
        ProviderArea.NURTURE_WEBHOOK,
        action="nurture webhook delivery",
        target_url=value,
    ).allowed


def _provider_gate_payload(decision: ProviderDecision) -> dict[str, Any]:
    return {
        "area": decision.area.value,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "action": decision.action,
        "external": decision.external,
        "live_mode": decision.live_mode,
        "target_url": _redacted_target_url(decision.target_url),
        "target_url_redacted": bool(decision.target_url),
    }


def _redacted_target_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        return "configured"
    host = parsed.hostname
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{host}{port}"


def _recipient_availability(lead: LeadRow, channel: str) -> dict[str, bool]:
    phone_present = bool(getattr(lead, "phone_e164", None))
    email_present = bool(getattr(lead, "email", None))
    if channel == "email":
        return {"phone_e164_present": False, "email_present": email_present}
    if channel in {"sms", "voice"}:
        return {"phone_e164_present": phone_present, "email_present": False}
    return {"phone_e164_present": phone_present, "email_present": email_present}


def _safety_message_for_lead(lead: LeadRow) -> str | None:
    safety_flags = {
        str(flag).strip().lower()
        for flag in (getattr(lead, "safety_flags", None) or [])
        if str(flag).strip()
    }
    urgency = str(getattr(lead, "urgency", "") or "").strip().lower()
    if urgency == "emergency" or bool(safety_flags & SAFETY_MESSAGE_FLAGS):
        return EMERGENCY_SAFETY_MESSAGE
    return None


def _local_communication_outbox(
    lead: LeadRow,
    *,
    webhook_url: str,
    source_event: str = "lead.unsold",
    channel_suppressions: Mapping[str, bool] | None = None,
    skip_webhook_gate: bool = False,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    safety_message = _safety_message_for_lead(lead)
    for channel, area in PROVIDER_CHANNELS:
        recipient = _recipient_availability(lead, channel)
        contact_available = any(recipient.values())
        suppressed = bool(channel_suppressions and channel_suppressions.get(channel))
        gate = provider_decision(
            area,
            action=f"{channel} nurture provider dispatch",
            requires_live_approval=True,
        )
        entries.append(
            {
                "channel": channel,
                "status": "suppressed_opt_out"
                if suppressed
                else "blocked_provider_approval"
                if contact_available and not gate.allowed
                else "provider_approved_pending_dispatch"
                if contact_available
                else "skipped_missing_contact",
                "template": LOCAL_OUTBOX_TEMPLATE,
                "source_event": source_event,
                "recipient": recipient,
                "provider_gate": _provider_gate_payload(gate),
                "would_contact_provider": False,
                "requires_action_approval": False if suppressed else True,
                "safety_message_required": safety_message is not None,
                "safety_message": safety_message,
            }
        )

    webhook_gate = provider_decision(
        ProviderArea.NURTURE_WEBHOOK, action="nurture webhook delivery"
    )
    if webhook_url and not skip_webhook_gate:
        webhook_gate = provider_decision(
            ProviderArea.NURTURE_WEBHOOK,
            action="nurture webhook delivery",
            target_url=webhook_url,
        )
    entries.append(
        {
            "channel": "nurture_webhook",
            "status": "suppressed_opt_out"
            if skip_webhook_gate and webhook_url
            else "not_configured"
            if not webhook_url
            else "local_dispatch_allowed"
            if webhook_gate.allowed and not webhook_gate.external
            else "provider_approved_pending_dispatch"
            if webhook_gate.allowed
            else "blocked_provider_approval",
            "template": LOCAL_OUTBOX_TEMPLATE,
            "source_event": source_event,
            "target_configured": bool(webhook_url),
            "provider_gate": _provider_gate_payload(webhook_gate),
            "would_contact_provider": False,
            "requires_action_approval": False if skip_webhook_gate else bool(webhook_gate.external),
            "safety_message_required": safety_message is not None,
            "safety_message": safety_message,
        }
    )
    return entries


def _outbox_channels(outreach_result: Mapping[str, Any]) -> list[str]:
    if outreach_result.get("reason") == "channel_suppression_pending":
        return []
    outbox = outreach_result.get("outbox")
    if not isinstance(outbox, list):
        return []
    excluded_statuses = {"skipped_missing_contact", "suppressed_opt_out"}
    return [
        str(entry["channel"])
        for entry in outbox
        if isinstance(entry, dict)
        and "channel" in entry
        and entry.get("status") not in excluded_statuses
    ]


async def _lead_is_suppressed(session: Any, lead: LeadRow) -> bool:
    clauses = []
    if lead.phone_e164:
        clauses.append(SuppressionEntry.phone_e164 == lead.phone_e164)
    if lead.email:
        clauses.append(SuppressionEntry.email == lead.email.strip().lower())
    if not clauses:
        return False
    suppression_id = await session.scalar(
        select(SuppressionEntry.id)
        .where(SuppressionEntry.status == "active", or_(*clauses))
        .limit(1)
    )
    return suppression_id is not None


async def _channel_suppression_states(session: Any, lead: LeadRow) -> dict[str, bool]:
    states = {channel: False for channel, _area in PROVIDER_CHANNELS}
    clauses = []
    phone_e164 = getattr(lead, "phone_e164", None)
    email = getattr(lead, "email", None)
    normalized_email = email.strip().lower() if isinstance(email, str) else None

    if phone_e164:
        clauses.append(
            and_(
                ChannelSuppression.channel.in_(("sms", "voice")),
                ChannelSuppression.phone_e164 == phone_e164,
            )
        )
    if normalized_email:
        clauses.append(
            and_(
                ChannelSuppression.channel == "email",
                ChannelSuppression.email == normalized_email,
            )
        )
    if not clauses:
        return states

    channels = await session.scalars(
        select(ChannelSuppression.channel).where(
            ChannelSuppression.status == "active", or_(*clauses)
        )
    )
    for channel in channels.all():
        if channel in states:
            states[str(channel)] = True
    return states


async def _send_nurture_outreach(
    lead: LeadRow,
    *,
    source_event: str = "lead.unsold",
    channel_suppressions: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    webhook_url = os.getenv("NURTURE_WEBHOOK_URL", "").strip()
    has_channel_suppression = bool(channel_suppressions and any(channel_suppressions.values()))
    outbox = _local_communication_outbox(
        lead,
        webhook_url=webhook_url,
        source_event=source_event,
        channel_suppressions=channel_suppressions,
        skip_webhook_gate=has_channel_suppression,
    )
    if has_channel_suppression:
        return {
            "sent": False,
            "reason": "channel_suppression_pending",
            "would_contact_provider": False,
            "outbox": outbox,
        }
    if not webhook_url:
        log.warning("nurture.webhook_not_configured", lead_id=str(lead.id))
        return {
            "sent": False,
            "reason": "local_outbox_pending",
            "would_contact_provider": False,
            "outbox": outbox,
        }
    if not _nurture_webhook_allowed(webhook_url):
        log.warning("nurture.webhook_not_allowed", lead_id=str(lead.id))
        return {
            "sent": False,
            "reason": "nurture webhook_url is not locally safe or approved",
            "would_contact_provider": False,
            "outbox": outbox,
        }
    webhook_entry = next(entry for entry in outbox if entry["channel"] == "nurture_webhook")
    if webhook_entry["provider_gate"]["external"]:
        return {
            "sent": False,
            "reason": "external_nurture_webhook_pending_action_approval",
            "would_contact_provider": False,
            "outbox": outbox,
        }

    payload = {
        "lead_id": str(lead.id),
        "name": lead.name,
        "phone_e164": lead.phone_e164,
        "email": lead.email,
        "city": lead.city,
        "state": lead.state,
        "requested_service": lead.requested_service,
        "damage_description": (lead.damage_description or "")[:500],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "sent": False,
            "reason": f"http_{exc.response.status_code}",
            "would_contact_provider": False,
            "outbox": outbox,
        }
    except Exception as exc:
        log.warning("nurture.webhook_failed", lead_id=str(lead.id), error=str(exc))
        return {
            "sent": False,
            "reason": type(exc).__name__,
            "would_contact_provider": False,
            "outbox": outbox,
        }

    return {
        "sent": True,
        "status_code": response.status_code,
        "would_contact_provider": False,
        "outbox": outbox,
    }


async def nurture_lead(context: Context) -> dict[str, Any]:
    workflow_input = context.workflow_input
    payload = workflow_input() if callable(workflow_input) else workflow_input
    lead_id = UUID(payload["lead_id"])
    bind_correlation_id(payload.get("correlation_id") or str(lead_id))
    source_event = str(payload.get("source_event") or "lead.unsold")
    from_state = PipelineState.REJECTED if source_event == "lead.rejected" else PipelineState.UNSOLD
    run_id = str(payload.get("run_id") or uuid4())

    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise ValueError(f"lead {lead_id} not found")
        if await _lead_is_suppressed(s, row):
            outreach_result = {"sent": False, "reason": "suppressed_opt_out"}
        else:
            channel_suppressions = await _channel_suppression_states(s, row)
            outreach_result = await _send_nurture_outreach(
                row,
                source_event=source_event,
                channel_suppressions=channel_suppressions,
            )
        sent = bool(outreach_result.get("sent"))
        to_state = PipelineState.NURTURED if sent else PipelineState.NURTURE_FAILED
        event_type = "lead.nurtured" if sent else "lead.nurture_failed"
        row.status = LeadStatus.NURTURED.value if sent else LeadStatus.NURTURE_FAILED.value
        await record_transition(
            s,
            lead_id=lead_id,
            from_state=from_state,
            to_state=to_state,
            event_type=event_type,
            task_name="agent_runtime.nurture_lead",
            workflow_run_id=run_id,
            payload={
                "source_event": source_event,
                "external_contact_made": sent,
                "contact_channels": ["webhook"] if sent else [],
                "outbox_channels": _outbox_channels(outreach_result),
                "outreach": outreach_result,
            },
        )

    if sent:
        emit_event("nurtured", lead_id=str(lead_id), service="agent-runtime")
        emit_metric("funnel.nurtured", lead_id=str(lead_id), service="agent-runtime")
        emit_metric(
            "unsold.recovery", lead_id=str(lead_id), service="agent-runtime", source=source_event
        )
    else:
        emit_event("nurture_failed", lead_id=str(lead_id), service="agent-runtime")
        emit_metric("funnel.nurture_failed", lead_id=str(lead_id), service="agent-runtime")
    return {
        "lead_id": str(lead_id),
        "status": LeadStatus.NURTURED.value if sent else LeadStatus.NURTURE_FAILED.value,
        "external_contact_made": sent,
        "outreach": outreach_result,
    }
