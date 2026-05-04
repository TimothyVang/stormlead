"""qualify_lead workflow: enrich + score a captured lead.

triggered by hatchet event "lead.enriched" emitted by enrich-worker.
inputs: payload with lead_id (uuid). outputs: structured qualification
result; persists damage_tier + qualification_score on the lead row;
emits "lead.qualified" or "lead.rejected" downstream.

All model calls route through LiteLLM so tracing, keys, and budgets stay centralized.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID, uuid4

from hatchet_sdk import Context, Hatchet
from stormlead_core import (
    ERROR_SINK,
    DamageTier,
    LeadClass,
    PipelineState,
    bind_correlation_id,
    emit_event,
    emit_metric,
    get_logger,
)
from stormlead_db import LeadRow, get_session, record_transition

from agent_runtime.execution import (
    ModelPolicy,
    TaskPolicy,
    emit_task_event,
    make_envelope,
    run_agent_task,
)

log = get_logger(__name__)


_QUALIFY_SYSTEM_PROMPT = """\
You are a lead-qualification analyst for a storm-chase tree-removal
lead-gen B2B SaaS. Given a homeowner lead with consent metadata, damage
description, and (when available) photo classifications, output strict JSON:

{
  "damage_tier": "tier_1_branches" | "tier_2_down_ground"
                 | "tier_3_on_structure" | "tier_4_life_safety",
  "qualification_score": <float 0.0..1.0>,
  "reasoning": "<short paragraph citing fields from the input>",
  "rejection_reason": "<set if score < 0.3, else null>"
}

Be conservative. If consent metadata is incomplete or the description
suggests no actual storm damage, score < 0.3 with a rejection_reason.
Do not echo PII back; reason in the abstract.
"""


async def qualify_lead(context: Context) -> dict[str, Any]:
    """fetches lead, runs opus qualification, returns the raw result.

    Returns the parsed qualification result after persisting lead status updates.
    """
    workflow_input = context.workflow_input
    payload = workflow_input() if callable(workflow_input) else workflow_input
    lead_id = UUID(payload["lead_id"])
    bind_correlation_id(payload.get("correlation_id") or str(lead_id))

    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise ValueError(f"lead {lead_id} not found")
        # minimal projection for the prompt; redact deeper pii at this layer
        lead_dict = {
            "city": row.city,
            "state": row.state,
            "damage_description": row.damage_description,
            "consent_at": str(row.consent_at) if row.consent_at else None,
            "page_url": row.page_url,
            "photo_count": len(row.photo_s3_keys or []),
        }

    correlation_id = None
    if isinstance(payload.get("correlation_id"), str):
        correlation_id = UUID(payload["correlation_id"])
    envelope = make_envelope(
        task_name="qualify_lead",
        workflow_name="QualifyLead",
        run_id=str(payload.get("run_id") or uuid4()),
        input_payload=payload,
        correlation_id=correlation_id,
        task_policy=TaskPolicy(timeout_seconds=120, retry_count=2),
        model_policy=ModelPolicy(
            primary_model="claude-opus-4-7",
            fallback_model="claude-sonnet-4-6",
            model_tier="premium",
            token_cap=12_000,
            cost_cap_usd=1.25,
        ),
    )
    emit_task_event(
        status="started",
        event_type="agent.task.started",
        envelope=envelope,
        attempt=1,
        model_used=envelope.primary_model,
        fallback_used=False,
    )
    try:
        result_text, usage = await run_agent_task(
            envelope=envelope,
            system_prompt=_QUALIFY_SYSTEM_PROMPT,
            prompt=str(lead_dict),
            allowed_tools=[],
        )
    except Exception as exc:
        emit_task_event(
            status="dead_lettered",
            event_type="agent.task.dead_lettered",
            envelope=envelope,
            attempt=envelope.retry_count + 1,
            model_used=envelope.fallback_model or envelope.primary_model,
            fallback_used=True,
            error=str(exc),
        )
        raise

    log.info("qualify.done", lead_id=str(lead_id), result_chars=len(result_text))

    try:
        parsed = _parse_qualification(result_text)
    except Exception as e:
        ERROR_SINK.report("agent-runtime", "qualify_parse", e, lead_id=str(lead_id))
        emit_metric("qualification.errors", lead_id=str(lead_id), service="agent-runtime")
        raise
    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise ValueError(f"lead {lead_id} not found")
        row.damage_tier = parsed["damage_tier"]
        row.qualification_score = parsed["qualification_score"]
        row.lead_class = _class_from_score(parsed["qualification_score"])
        row.qualification_reason = parsed["reasoning"]
        row.rejection_reason = parsed["rejection_reason"]
        row.status = "rejected" if parsed["rejection_reason"] else "qualified"
        to_state = PipelineState.REJECTED if parsed["rejection_reason"] else PipelineState.QUALIFIED
        await record_transition(
            s,
            lead_id=lead_id,
            from_state=PipelineState.ENRICHED,
            to_state=to_state,
            event_type="lead.rejected" if parsed["rejection_reason"] else "lead.qualified",
            task_name="agent_runtime.qualify_lead",
            workflow_run_id=envelope.run_id,
            payload={
                "damage_tier": parsed["damage_tier"],
                "qualification_score": parsed["qualification_score"],
                "lead_class": row.lead_class,
                "rejection_reason": parsed["rejection_reason"],
                "reasoning_summary": _reasoning_summary(parsed["reasoning"]),
                "model_used": str(usage["model_used"]),
                "fallback_used": bool(usage["fallback_used"]),
                "duration_ms": int(usage["duration_ms"]),
                "estimated_input_tokens": int(usage["estimated_input_tokens"]),
                "estimated_output_tokens": int(usage["estimated_output_tokens"]),
                "estimated_cost_usd": float(usage["estimated_cost_usd"]),
            },
        )

    stage = "qualified" if not parsed["rejection_reason"] else "unsold"
    emit_event(stage, lead_id=str(lead_id), service="agent-runtime")
    emit_metric(f"funnel.{stage}", lead_id=str(lead_id), service="agent-runtime")
    emit_metric(
        "qualification.latency_ms",
        value=float(usage["duration_ms"]),
        lead_id=str(lead_id),
        service="agent-runtime",
    )
    emit_metric(
        "llm.cost_per_lead",
        value=float(usage["estimated_cost_usd"]),
        lead_id=str(lead_id),
        service="agent-runtime",
        model=str(usage["model_used"]),
    )

    event_name = "lead.rejected" if parsed["rejection_reason"] else "lead.qualified"
    Hatchet(debug=False).event.push(
        event_name,
        {
            "lead_id": str(lead_id),
            "run_id": envelope.run_id,
            "correlation_id": str(lead_id),
            "source_event": event_name,
        },
    )
    emit_task_event(
        status="success",
        event_type="agent.task.succeeded",
        envelope=envelope,
        attempt=1,
        model_used=str(usage["model_used"]),
        fallback_used=bool(usage["fallback_used"]),
        duration_ms=int(usage["duration_ms"]),
        estimated_input_tokens=int(usage["estimated_input_tokens"]),
        estimated_output_tokens=int(usage["estimated_output_tokens"]),
        estimated_cost_usd=float(usage["estimated_cost_usd"]),
    )
    return {"lead_id": str(lead_id), **parsed}


def _parse_qualification(result_text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", result_text, re.DOTALL)
    if not match:
        raise ValueError("qualification result did not contain json")
    data = json.loads(match.group(0))
    damage_tier = DamageTier(data["damage_tier"]).value
    score = float(data["qualification_score"])
    if score < 0 or score > 1:
        raise ValueError("qualification_score must be between 0 and 1")
    return {
        "damage_tier": damage_tier,
        "qualification_score": score,
        "reasoning": str(data.get("reasoning") or ""),
        "rejection_reason": data.get("rejection_reason"),
    }


def _class_from_score(score: float) -> str:
    if score >= 0.85:
        return LeadClass.A.value
    if score >= 0.6:
        return LeadClass.B.value
    if score >= 0.3:
        return LeadClass.C.value
    return LeadClass.D.value


def _reasoning_summary(value: str, *, limit: int = 320) -> str:
    summary = re.sub(r"\s+", " ", value).strip()
    summary = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", summary, flags=re.I
    )
    summary = re.sub(r"\+\d{8,15}", "[redacted-phone]", summary)
    return summary[:limit]
