from __future__ import annotations

from typing import Any

from hatchet_sdk import Context
from stormlead_core import get_logger

log = get_logger(__name__)


async def triage_return_request(context: Context) -> dict[str, Any]:
    payload = context.workflow_input()
    recommendation = {
        "return_request_id": payload.get("return_request_id"),
        "recommended_state": "UNDER_REVIEW",
        "confidence": 0.5,
        "human_approval_required": True,
        "rationale": "Evidence bundle present; requires human review before approval/denial.",
    }
    log.info("returns.triage_recommended", return_request_id=payload.get("return_request_id"))
    return recommendation
