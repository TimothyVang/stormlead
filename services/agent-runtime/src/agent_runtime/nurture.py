from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from hatchet_sdk import Context
from stormlead_core import LeadStatus, PipelineState, bind_correlation_id, emit_event, emit_metric
from stormlead_db import LeadRow, get_session, record_transition


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
        row.status = LeadStatus.NURTURED.value
        await record_transition(
            s,
            lead_id=lead_id,
            from_state=from_state,
            to_state=PipelineState.NURTURED,
            event_type="lead.nurtured",
            task_name="agent_runtime.nurture_lead",
            workflow_run_id=run_id,
            payload={"source_event": source_event},
        )

    emit_event("nurtured", lead_id=str(lead_id), service="agent-runtime")
    emit_metric("funnel.nurtured", lead_id=str(lead_id), service="agent-runtime")
    emit_metric(
        "unsold.recovery", lead_id=str(lead_id), service="agent-runtime", source=source_event
    )
    return {"lead_id": str(lead_id), "status": LeadStatus.NURTURED.value}
