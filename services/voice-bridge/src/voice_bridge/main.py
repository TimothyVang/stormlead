from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse
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


class InboundCallPreviewRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=128)
    from_phone_e164: str = Field(min_length=8, max_length=20)
    to_phone_e164: str = Field(min_length=8, max_length=20)
    transcript_text: str | None = Field(default=None, max_length=10_000)
    photo_link_url: str | None = Field(default=None, max_length=2_048)
    consent_text: str | None = Field(default=None, max_length=500)
    requested_service: str = Field(default="tree_removal", min_length=1, max_length=64)
    damage_description: str | None = Field(default=None, max_length=2_000)
    power_line_involved: bool = False
    injury_reported: bool = False
    active_danger: bool = False

    @field_validator("from_phone_e164", "to_phone_e164")
    @classmethod
    def phone_must_be_e164(cls, value: str) -> str:
        if not value.startswith("+"):
            raise ValueError("phone number must start with +")
        return value

    @field_validator("photo_link_url")
    @classmethod
    def photo_link_must_be_http_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("photo_link_url must be an http(s) URL")
        return value


class InboundCallPreviewResponse(BaseModel):
    mode: Literal["local_preview"]
    call_id: str
    intake_status: Literal[
        "ready_for_operator_review",
        "held_for_safety_review",
        "blocked_missing_required_fields",
    ]
    unsafe_call_held: bool
    blocked_reasons: list[str]
    modeled_fields: dict[str, bool]
    live_call_allowed: bool
    would_contact_phone_provider: bool
    provider_action: Literal["parked_until_explicit_approval"]
    next_safe_action: str
    disclosure_script: list[str]
    transcript_policy: dict[str, str | int | bool]
    photo_link_policy: dict[str, str | bool]


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


@app.post("/v1/inbound/preview")
async def preview_inbound_call(payload: InboundCallPreviewRequest) -> InboundCallPreviewResponse:
    blocked_reasons: list[str] = []
    intake_status: Literal[
        "ready_for_operator_review",
        "held_for_safety_review",
        "blocked_missing_required_fields",
    ]
    transcript_present = bool((payload.transcript_text or "").strip())
    consent_present = bool((payload.consent_text or "").strip())
    photo_link_present = bool(payload.photo_link_url)
    unsafe_call = payload.power_line_involved or payload.injury_reported or payload.active_danger

    if not transcript_present:
        blocked_reasons.append("missing_transcript_text")
    if not consent_present:
        blocked_reasons.append("missing_consent_text")
    if unsafe_call:
        blocked_reasons.append("unsafe_call_safety_escalation")

    if unsafe_call:
        intake_status = "held_for_safety_review"
        next_safe_action = (
            "operator_reviews_safety_hold_and_directs_homeowner_to_emergency_or_utility_first"
        )
    elif blocked_reasons:
        intake_status = "blocked_missing_required_fields"
        next_safe_action = "collect_required_call_intake_fields_before_operator_review"
    else:
        intake_status = "ready_for_operator_review"
        next_safe_action = "operator_may_review_intake_before_any_future_provider_action"

    return InboundCallPreviewResponse(
        mode="local_preview",
        call_id=payload.call_id,
        intake_status=intake_status,
        unsafe_call_held=unsafe_call,
        blocked_reasons=blocked_reasons,
        modeled_fields={
            "call_id": bool(payload.call_id.strip()),
            "from_phone_e164": True,
            "to_phone_e164": True,
            "transcript_text": transcript_present,
            "photo_link_url": photo_link_present,
            "consent_text": consent_present,
            "requested_service": bool(payload.requested_service.strip()),
            "damage_description": bool((payload.damage_description or "").strip()),
            "safety_flags": unsafe_call,
        },
        live_call_allowed=False,
        would_contact_phone_provider=False,
        provider_action="parked_until_explicit_approval",
        next_safe_action=next_safe_action,
        disclosure_script=[
            "Treat inbound voice intake as a local preview until an approved phone provider is configured.",
            "Capture transcript, consent, service, and photo-link evidence before any operator review.",
            "For power lines, injuries, or active danger, hold automation and tell the homeowner to contact emergency services or the utility first.",
        ],
        transcript_policy={
            "stored_locally_only": True,
            "max_characters": 10_000,
            "pii_minimization_required": True,
            "summary": "Use transcript text only for local operator review until voice provider approval exists.",
        },
        photo_link_policy={
            "allowed": True,
            "required_for_auto_sale": False,
            "would_fetch_remote_url": False,
            "summary": "Photo links are modeled for review but are not fetched or sent to any provider by this preview.",
        },
    )
