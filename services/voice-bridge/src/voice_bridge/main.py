from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator

MAX_FOLLOW_UP_ATTEMPTS = 3
FOLLOW_UP_ELIGIBLE_STATUSES = {"qualified", "unsold", "buyer_rejected"}


class FollowUpPreviewRequest(BaseModel):
    lead_id: UUID
    phone_e164: str = Field(min_length=8, max_length=20)
    lead_status: str = Field(default="qualified", min_length=1, max_length=64)
    consent_text: str = Field(min_length=1, max_length=500)
    attempt_count: int = Field(default=0, ge=0)

    @field_validator("phone_e164")
    @classmethod
    def phone_must_be_e164(cls, value: str) -> str:
        if not value.startswith("+"):
            raise ValueError("phone_e164 must start with +")
        return value


class FollowUpPreviewResponse(BaseModel):
    mode: Literal["local_preview"]
    lead_id: UUID
    eligible_for_follow_up: bool
    blocked_reasons: list[str]
    live_call_allowed: bool
    would_contact_phone_provider: bool
    provider_action: Literal["parked_until_explicit_approval"]
    next_safe_action: str
    max_attempts: int
    remaining_attempts: int
    disclosure_script: list[str]
    voicemail_policy: dict[str, str | int | bool]


app = FastAPI(title="stormlead voice-bridge")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str | bool]:
    return {"status": "ready", "local_preview_only": True}


@app.post("/v1/follow-up/preview")
async def preview_follow_up(payload: FollowUpPreviewRequest) -> FollowUpPreviewResponse:
    blocked_reasons: list[str] = []
    normalized_status = payload.lead_status.strip().lower()
    if normalized_status not in FOLLOW_UP_ELIGIBLE_STATUSES:
        blocked_reasons.append("lead_status_not_follow_up_eligible")
    if not payload.consent_text.strip():
        blocked_reasons.append("missing_consent_text")
    if payload.attempt_count >= MAX_FOLLOW_UP_ATTEMPTS:
        blocked_reasons.append("max_attempts_reached")

    eligible = not blocked_reasons
    remaining_attempts = max(0, MAX_FOLLOW_UP_ATTEMPTS - payload.attempt_count)
    next_safe_action = (
        "operator_may_review_and_approve_future_provider_action"
        if eligible
        else "resolve_blocked_reasons_before_follow_up"
    )
    return FollowUpPreviewResponse(
        mode="local_preview",
        lead_id=payload.lead_id,
        eligible_for_follow_up=eligible,
        blocked_reasons=blocked_reasons,
        live_call_allowed=False,
        would_contact_phone_provider=False,
        provider_action="parked_until_explicit_approval",
        next_safe_action=next_safe_action,
        max_attempts=MAX_FOLLOW_UP_ATTEMPTS,
        remaining_attempts=remaining_attempts,
        disclosure_script=[
            "Identify StormLead as a referral marketplace, not the tree-service contractor.",
            "Reference the submitted tree-damage request and consent before any future call.",
            "For power lines, injuries, active danger, or blocked access, tell the homeowner to contact emergency services or the utility first.",
        ],
        voicemail_policy={
            "allowed": True,
            "max_seconds": 30,
            "template": "Briefly identify StormLead, reference the submitted request, and ask the homeowner to call back if they still want contractor help.",
            "pii_heavy_content_allowed": False,
        },
    )
