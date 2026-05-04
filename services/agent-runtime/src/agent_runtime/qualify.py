from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from claude_agent_sdk import query
from hatchet_sdk import Context
from stormlead_core import DamageTier, LeadClass, get_logger
from stormlead_db import LeadRow, get_session

from agent_runtime.auth import get_agent_options
from agent_runtime.policy import Timer, flow_enabled, get_policy
from agent_runtime.telemetry import record_run

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
"""


async def qualify_lead(context: Context) -> dict[str, Any]:
    if not flow_enabled("qualify"):
        return {"skipped": True, "reason": "qualify flow disabled"}
    payload = context.workflow_input()
    lead_id = UUID(payload["lead_id"])

    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise ValueError(f"lead {lead_id} not found")
        lead_dict = {
            "city": row.city,
            "state": row.state,
            "damage_description": row.damage_description,
            "consent_at": str(row.consent_at) if row.consent_at else None,
            "page_url": row.page_url,
            "photo_count": len(row.photo_s3_keys or []),
        }

    policy = get_policy("qualify_complex", escalate=bool(payload.get("escalate")))
    result_text = ""
    outcome = "success"
    err_msg = None
    with Timer() as timer:
        for attempt in range(policy.retries + 1):
            try:
                options = get_agent_options(
                    "qualify_complex",
                    system_prompt=_QUALIFY_SYSTEM_PROMPT,
                    allowed_tools=[],
                    model=policy.model if attempt == 0 else (policy.fallback_model or policy.model),
                    max_tokens=policy.max_tokens,
                )
                async for message in query(prompt=str(lead_dict), options=options):
                    content = getattr(message, "content", None)
                    if content:
                        result_text += str(content)
                break
            except Exception as exc:
                outcome = "failed"
                err_msg = str(exc)
                if attempt >= policy.retries:
                    raise

    parsed = _parse_qualification(result_text)
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

    await record_run(
        flow_name="qualify",
        workload="qualify_complex",
        model=policy.model,
        max_tokens=policy.max_tokens,
        retries=policy.retries,
        latency_ms=timer.elapsed_ms,
        estimated_cost_usd=0.0,
        outcome=outcome,
        error=err_msg,
    )
    log.info("qualify.done", lead_id=str(lead_id), latency_ms=timer.elapsed_ms)
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
