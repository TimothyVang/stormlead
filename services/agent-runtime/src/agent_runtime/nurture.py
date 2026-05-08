from __future__ import annotations

import os
from typing import Any
from uuid import UUID, uuid4

import httpx
from hatchet_sdk import Context
from stormlead_core import (
    LeadStatus,
    PipelineState,
    bind_correlation_id,
    emit_event,
    emit_metric,
    get_logger,
)
from stormlead_db import LeadRow, get_session, record_transition

log = get_logger(__name__)


async def _send_nurture_outreach(lead: LeadRow) -> dict[str, Any]:
    webhook_url = os.getenv("NURTURE_WEBHOOK_URL", "").strip()
    if not webhook_url:
        log.warning("nurture.webhook_not_configured", lead_id=str(lead.id))
        return {"sent": False, "reason": "NURTURE_WEBHOOK_URL not set"}

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
        return {"sent": False, "reason": f"http_{exc.response.status_code}"}
    except Exception as exc:
        log.warning("nurture.webhook_failed", lead_id=str(lead.id), error=str(exc))
        return {"sent": False, "reason": type(exc).__name__}

    return {"sent": True, "status_code": response.status_code}


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
        outreach_result = await _send_nurture_outreach(row)
        row.status = LeadStatus.NURTURED.value
        await record_transition(
            s,
            lead_id=lead_id,
            from_state=from_state,
            to_state=PipelineState.NURTURED,
            event_type="lead.nurtured",
            task_name="agent_runtime.nurture_lead",
            workflow_run_id=run_id,
            payload={
                "source_event": source_event,
                "external_contact_made": bool(outreach_result.get("sent")),
                "contact_channels": ["webhook"] if outreach_result.get("sent") else [],
                "outreach": outreach_result,
            },
        )

    emit_event("nurtured", lead_id=str(lead_id), service="agent-runtime")
    emit_metric("funnel.nurtured", lead_id=str(lead_id), service="agent-runtime")
    emit_metric(
        "unsold.recovery", lead_id=str(lead_id), service="agent-runtime", source=source_event
    )
    return {
        "lead_id": str(lead_id),
        "status": LeadStatus.NURTURED.value,
        "external_contact_made": bool(outreach_result.get("sent")),
        "outreach": outreach_result,
    }
