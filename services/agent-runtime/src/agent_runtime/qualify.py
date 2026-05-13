"""qualify_lead workflow: enrich + score a captured lead.

triggered by hatchet event "lead.enriched" emitted by enrich-worker.
inputs: payload with lead_id (uuid). outputs: structured qualification
result; persists damage_tier + qualification_score on the lead row;
emits "lead.qualified" or "lead.rejected" downstream.

All model calls route through LiteLLM so tracing, keys, and budgets stay centralized.
"""

from __future__ import annotations

import json
import os
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
HIGH_RISK_SAFETY_FLAGS = frozenset(
    {"power_line", "injury", "active_danger", "roof_impact", "structure_impact"}
)
REVIEW_SAFETY_FLAGS = HIGH_RISK_SAFETY_FLAGS | frozenset({"emergency"})
VISIBLE_RISK_LEVELS = frozenset({"low", "medium", "high"})
RECOMMENDED_FOLLOWUPS = frozenset({"route", "human_review", "reject"})
ESTIMATED_JOB_SIZES = frozenset({"small", "medium", "large", "emergency"})
_STREET_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9 .'-]{1,80}\b"
    r"(?:st|street|ave|avenue|rd|road|dr|drive|ln|lane|ct|court|blvd|boulevard|"
    r"way|pl|place|terrace|ter|trail|trl)\b\.?",
    re.I,
)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)")
_CONTACT_NAME_RE = re.compile(r"\b(call|contact|ask for)\s+[A-Z][A-Za-z'-]*", re.I)


_QUALIFY_SYSTEM_PROMPT = """\
You are a lead-qualification analyst for a storm-chase tree-removal
lead-gen B2B SaaS. Given a homeowner lead with consent metadata, damage
description, and (when available) photo classifications, output strict JSON:

{
  "damage_tier": "tier_1_branches" | "tier_2_down_ground"
                  | "tier_3_on_structure" | "tier_4_life_safety",
  "qualification_score": <float 0.0..1.0>,
  "damage_summary": "<one sentence non-PII summary of the visible tree damage>",
  "visible_risk_level": "low" | "medium" | "high",
  "estimated_job_size": "small" | "medium" | "large" | "emergency",
  "buyer_notes": "<short non-PII note a tree-service buyer can act on>",
  "safety_flags": ["power_line" | "injury" | "active_danger"
                   | "roof_impact" | "structure_impact" | "emergency"],
  "recommended_followup": "route" | "human_review" | "reject",
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

    simulation_result: dict[str, Any] | None = None
    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise ValueError(f"lead {lead_id} not found")
        simulation_result = _local_simulation_result(row)
        # minimal projection for the prompt; redact deeper pii at this layer
        lead_dict = {
            "city": row.city,
            "state": row.state,
            "damage_description": _reasoning_summary(row.damage_description or "", limit=500),
            "damage_type": row.damage_type,
            "urgency": row.urgency,
            "safety_flags": row.safety_flags or [],
            "consent_at": str(row.consent_at) if row.consent_at else None,
            "page_url": row.page_url,
            "photo_count": len(row.photo_s3_keys or []),
            "location_verification_status": row.location_verification_status,
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
        if simulation_result is not None:
            parsed = simulation_result
            usage: dict[str, float | int | str | bool] = {
                "duration_ms": 0,
                "estimated_input_tokens": 0,
                "estimated_output_tokens": 0,
                "estimated_cost_usd": 0.0,
                "model_used": "local-simulation",
                "fallback_used": False,
            }
        else:
            result_text, usage = await run_agent_task(
                envelope=envelope,
                system_prompt=_QUALIFY_SYSTEM_PROMPT,
                prompt=str(lead_dict),
                allowed_tools=[],
            )
            log.info("qualify.done", lead_id=str(lead_id), result_chars=len(result_text))
            try:
                parsed = _parse_qualification(result_text)
            except Exception as e:
                ERROR_SINK.report("agent-runtime", "qualify_parse", e, lead_id=str(lead_id))
                emit_metric("qualification.errors", lead_id=str(lead_id), service="agent-runtime")
                raise
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

    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise ValueError(f"lead {lead_id} not found")
        to_state = _apply_qualification_result(row, parsed)
        rejection_reason = _qualification_rejection_reason(parsed)
        await record_transition(
            s,
            lead_id=lead_id,
            from_state=PipelineState.ENRICHED,
            to_state=to_state,
            event_type="lead.rejected" if rejection_reason else "lead.qualified",
            task_name="agent_runtime.qualify_lead",
            workflow_run_id=envelope.run_id,
            payload={
                "damage_tier": parsed["damage_tier"],
                "qualification_score": parsed["qualification_score"],
                "damage_summary": parsed.get("damage_summary"),
                "visible_risk_level": parsed.get("visible_risk_level"),
                "estimated_job_size": parsed.get("estimated_job_size"),
                "buyer_notes": parsed.get("buyer_notes"),
                "safety_flags": parsed.get("safety_flags"),
                "recommended_followup": parsed.get("recommended_followup"),
                "lead_class": row.lead_class,
                "rejection_reason": rejection_reason,
                "reasoning_summary": _reasoning_summary(parsed["reasoning"]),
                "model_used": str(usage["model_used"]),
                "fallback_used": bool(usage["fallback_used"]),
                "duration_ms": int(usage["duration_ms"]),
                "estimated_input_tokens": int(usage["estimated_input_tokens"]),
                "estimated_output_tokens": int(usage["estimated_output_tokens"]),
                "estimated_cost_usd": float(usage["estimated_cost_usd"]),
            },
        )

    rejection_reason = _qualification_rejection_reason(parsed)
    stage = "qualified" if not rejection_reason else "unsold"
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

    event_name = "lead.rejected" if rejection_reason else "lead.qualified"
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
    visible_risk_value = data.get("visible_risk_level")
    if not isinstance(visible_risk_value, str) or not visible_risk_value.strip():
        raise ValueError("visible_risk_level is required")
    visible_risk_level = visible_risk_value.strip().lower()
    if visible_risk_level not in VISIBLE_RISK_LEVELS:
        raise ValueError("visible_risk_level must be low, medium, or high")
    estimated_job_size_value = data.get("estimated_job_size")
    if not isinstance(estimated_job_size_value, str) or not estimated_job_size_value.strip():
        raise ValueError("estimated_job_size is required")
    estimated_job_size = estimated_job_size_value.strip().lower()
    if estimated_job_size not in ESTIMATED_JOB_SIZES:
        raise ValueError("estimated_job_size must be small, medium, large, or emergency")
    recommended_followup_value = data.get("recommended_followup")
    if not isinstance(recommended_followup_value, str) or not recommended_followup_value.strip():
        raise ValueError("recommended_followup is required")
    recommended_followup = recommended_followup_value.strip().lower()
    if recommended_followup not in RECOMMENDED_FOLLOWUPS:
        raise ValueError("recommended_followup must be route, human_review, or reject")
    safety_flags = _parse_model_safety_flags(data.get("safety_flags"))
    return {
        "damage_tier": damage_tier,
        "qualification_score": score,
        "damage_summary": _required_review_text(data, "damage_summary", limit=240),
        "visible_risk_level": visible_risk_level,
        "estimated_job_size": estimated_job_size,
        "buyer_notes": _required_review_text(data, "buyer_notes", limit=320),
        "safety_flags": safety_flags,
        "recommended_followup": recommended_followup,
        "reasoning": _controlled_model_reasoning(
            damage_tier=damage_tier,
            score=score,
            visible_risk_level=visible_risk_level,
            estimated_job_size=estimated_job_size,
            recommended_followup=recommended_followup,
        ),
        "rejection_reason": "model_rejected" if data.get("rejection_reason") else None,
    }


def _required_review_text(data: dict[str, Any], key: str, *, limit: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return _reasoning_summary(value, limit=limit)


def _parse_model_safety_flags(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("safety_flags is required")
    safety_flags = _normalized_safety_flags(value)
    unsupported = safety_flags - REVIEW_SAFETY_FLAGS
    if unsupported:
        raise ValueError("safety_flags contains unsupported value")
    return sorted(safety_flags)


def _normalized_safety_flags(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(flag).strip().lower() for flag in value if str(flag).strip()}


def _controlled_model_reasoning(
    *,
    damage_tier: str,
    score: float,
    visible_risk_level: str,
    estimated_job_size: str,
    recommended_followup: str,
) -> str:
    return (
        f"Model classified {damage_tier} with score {score:.2f}, "
        f"visible risk {visible_risk_level}, estimated job size {estimated_job_size}, "
        f"and follow-up {recommended_followup}."
    )


def _local_structured_review(tier: str, *, safety_flags: set[str]) -> dict[str, Any]:
    if tier == DamageTier.TIER_3_ON_STRUCTURE.value:
        return {
            "damage_summary": "Tree impact on a structure or vehicle was reported.",
            "visible_risk_level": "medium",
            "estimated_job_size": "large",
            "buyer_notes": "Verify structure involvement, access constraints, and equipment needs.",
            "safety_flags": sorted(safety_flags),
        }
    if tier == DamageTier.TIER_1_BRANCHES.value:
        return {
            "damage_summary": "Branch or small cleanup request was reported.",
            "visible_risk_level": "low",
            "estimated_job_size": "small",
            "buyer_notes": "Confirm access, debris volume, and disposal needs before dispatch.",
            "safety_flags": sorted(safety_flags),
        }
    return {
        "damage_summary": "Downed tree or yard obstruction was reported.",
        "visible_risk_level": "medium" if "emergency" in safety_flags else "low",
        "estimated_job_size": "emergency" if "emergency" in safety_flags else "medium",
        "buyer_notes": "Confirm tree size, access path, and whether heavy equipment is needed.",
        "safety_flags": sorted(safety_flags),
    }


def _local_simulation_result(row: LeadRow) -> dict[str, Any] | None:
    markers = [
        row.campaign_source,
        row.campaign_id,
        row.first_touch_source,
        row.last_touch_source,
    ]
    local_marker = any(
        isinstance(value, str) and value.startswith(("local_", "simulation_", "v1-simulation"))
        for value in markers
    )
    if not local_marker and os.getenv("STORMLEAD_LOCAL_SIMULATION_QUALIFY") != "true":
        return None

    scenario = " ".join(str(value or "") for value in markers).lower()
    low_quality = (
        "reject" in scenario
        or "low_quality" in scenario
        or bool(row.blocked_for_fraud)
        or float(row.score or 1.0) < 0.3
    )
    if low_quality:
        return {
            "damage_tier": DamageTier.TIER_1_BRANCHES.value,
            "qualification_score": 0.2,
            "damage_summary": "Low-quality synthetic lead with no sellable storm-damage job identified.",
            "visible_risk_level": "low",
            "estimated_job_size": "small",
            "buyer_notes": "Do not route; local simulation marked this lead low quality.",
            "safety_flags": sorted(_row_safety_flags(row)),
            "recommended_followup": "reject",
            "reasoning": "Local simulation marked the synthetic lead as low quality.",
            "rejection_reason": "local_simulation_low_quality",
        }

    safety_flags = _row_safety_flags(row)
    damage_type = str(getattr(row, "damage_type", "") or "").lower()
    if safety_flags & HIGH_RISK_SAFETY_FLAGS:
        return {
            "damage_tier": DamageTier.TIER_4_LIFE_SAFETY.value,
            "qualification_score": 0.7,
            "damage_summary": "Life-safety tree damage signal reported; operator review is required.",
            "visible_risk_level": "high",
            "estimated_job_size": "emergency",
            "buyer_notes": "Hold for operator review before any buyer delivery.",
            "safety_flags": sorted(safety_flags),
            "recommended_followup": "human_review",
            "reasoning": "Local simulation detected a life-safety tree damage flag requiring human review before routing.",
            "rejection_reason": None,
        }
    if damage_type in {"roof_impact", "tree_on_structure", "structure_impact"}:
        tier = DamageTier.TIER_3_ON_STRUCTURE.value
    elif damage_type in {"broken_branch", "branch_removal", "stump"}:
        tier = DamageTier.TIER_1_BRANCHES.value
    else:
        tier = DamageTier.TIER_2_DOWN_GROUND.value

    return {
        "damage_tier": tier,
        "qualification_score": max(float(row.score or 0.85), 0.85),
        **_local_structured_review(tier, safety_flags=safety_flags),
        "recommended_followup": "route",
        "reasoning": "Local simulation marked the synthetic storm-damage lead as qualified.",
        "rejection_reason": None,
    }


def _class_from_score(score: float) -> str:
    if score >= 0.85:
        return LeadClass.A.value
    if score >= 0.6:
        return LeadClass.B.value
    if score >= 0.3:
        return LeadClass.C.value
    return LeadClass.D.value


def _apply_qualification_result(row: LeadRow, parsed: dict[str, Any]) -> PipelineState:
    row.damage_tier = parsed["damage_tier"]
    row.qualification_score = parsed["qualification_score"]
    row.damage_summary = parsed["damage_summary"]
    row.visible_risk_level = parsed["visible_risk_level"]
    row.estimated_job_size = parsed["estimated_job_size"]
    row.buyer_notes = parsed["buyer_notes"]
    row.safety_flags = sorted(
        (_row_safety_flags(row) | _normalized_safety_flags(parsed["safety_flags"]))
        & REVIEW_SAFETY_FLAGS
    )
    row.qualification_reason = parsed["reasoning"]

    if row.is_resale:
        row.lead_class = LeadClass.D.value
        row.rejection_reason = "resale_duplicate"
        row.status = "rejected"
        return PipelineState.REJECTED

    row.lead_class = _class_from_score(parsed["qualification_score"])
    rejection_reason = _qualification_rejection_reason(parsed)
    row.rejection_reason = rejection_reason
    if _qualification_requires_human_review(row, parsed) and not rejection_reason:
        row.hold_for_review = True
        row.status = "qualified"
        return PipelineState.QUALIFIED
    row.status = "rejected" if rejection_reason else "qualified"
    return PipelineState.REJECTED if rejection_reason else PipelineState.QUALIFIED


def _qualification_rejection_reason(parsed: dict[str, Any]) -> str | None:
    if parsed.get("rejection_reason"):
        return str(parsed["rejection_reason"])
    if parsed.get("recommended_followup") == "reject":
        return "model_recommended_reject"
    return None


def _qualification_requires_human_review(row: LeadRow, parsed: dict[str, Any]) -> bool:
    return (
        parsed["damage_tier"] == DamageTier.TIER_4_LIFE_SAFETY.value
        or bool(_row_safety_flags(row) & HIGH_RISK_SAFETY_FLAGS)
        or parsed.get("visible_risk_level") == "high"
        or parsed.get("recommended_followup") == "human_review"
    )


def _row_safety_flags(row: LeadRow) -> set[str]:
    raw_flags = getattr(row, "safety_flags", None) or []
    return {
        str(flag).strip().lower()
        for flag in raw_flags
        if str(flag).strip().lower() in REVIEW_SAFETY_FLAGS
    }


def _reasoning_summary(value: str, *, limit: int = 320) -> str:
    summary = re.sub(r"\s+", " ", value).strip()
    summary = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", summary, flags=re.I
    )
    summary = _PHONE_RE.sub("[redacted-phone]", summary)
    summary = re.sub(r"\+\d{8,15}", "[redacted-phone]", summary)
    summary = _STREET_ADDRESS_RE.sub("[redacted-address]", summary)
    summary = _CONTACT_NAME_RE.sub(lambda match: f"{match.group(1)} [redacted-name]", summary)
    return summary[:limit]
