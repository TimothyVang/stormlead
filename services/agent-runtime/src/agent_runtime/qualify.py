"""qualify_lead workflow: enrich + score a captured lead.

triggered by hatchet event "lead.captured" emitted by form-receiver.
inputs: payload with lead_id (uuid). outputs: structured qualification
result; persists damage_tier + qualification_score on the lead row;
emits "lead.qualified" or "lead.rejected" downstream.

uses opus via oauth. the volume is bounded (one call per inbound lead;
mvp scale ~10-100/day) so flat-rate subscription billing is the right
fit. complex multi-step reasoning over pii is opus's strength.
"""

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

    persistence + downstream event emission are TODO — wire when
    skill_proposals + lead-status update paths land. for the v1 scaffold
    this returns the raw model output so traces show the full call.
    """
    payload = context.workflow_input()
    lead_id = UUID(payload["lead_id"])

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

    options = get_agent_options(
        "qualify_complex",
        system_prompt=_QUALIFY_SYSTEM_PROMPT,
        allowed_tools=[],  # pure reasoning; no tool calls needed
    )

    result_text = ""
    async for message in query(prompt=str(lead_dict), options=options):
        # collect any text-bearing payload from the message stream
        content = getattr(message, "content", None)
        if content:
            result_text += str(content)

    log.info("qualify.done", lead_id=str(lead_id), result_chars=len(result_text))

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

    # TODO: emit lead.qualified / lead.rejected after Hatchet event emission is
    # wrapped in a small shared helper. Persistence is the paid-pilot gate.
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
