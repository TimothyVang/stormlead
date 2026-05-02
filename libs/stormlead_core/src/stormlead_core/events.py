"""domain event envelopes. one type per logical event.

these are the canonical pydantic shapes for cross-service events. nats was
removed in commit cfb2c15; consumers now use hatchet event triggers (when
agent-runtime lands) or postgres listen/notify for v1.

logical event topics (kept for documentation / future re-introduction):
  storm.detected
  lead.captured
  lead.qualified | lead.rejected | lead.posted | lead.sold | lead.unsold
  call.started | call.answered | call.ended | call.transcribed
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from stormlead_core.models import DamageTier, Lead, Storm


class _Envelope(BaseModel):
    """all events share this envelope so consumers can route uniformly."""

    event_id: UUID
    event_type: str
    occurred_at: datetime
    correlation_id: UUID | None = None  # ties multi-step workflows together
    causation_id: UUID | None = None  # which event caused this one


class StormDetected(_Envelope):
    event_type: Literal["storm.detected"] = "storm.detected"
    storm: Storm


class StormEvent(_Envelope):
    """umbrella for any storm-related state change."""

    event_type: Literal[
        "storm.warning_issued",
        "storm.landfall",
        "storm.post_impact",
        "storm.declared",
    ]
    storm: Storm


class LeadCaptured(_Envelope):
    event_type: Literal["lead.captured"] = "lead.captured"
    lead: Lead


class LeadEvent(_Envelope):
    event_type: Literal[
        "lead.qualified",
        "lead.rejected",
        "lead.posted",
        "lead.sold",
        "lead.unsold",
        "lead.dialed",
        "lead.contacted",
    ]
    lead_id: UUID
    buyer_id: UUID | None = None
    bid_cents: int | None = None
    reason: str | None = None


class PingPostResult(_Envelope):
    """emitted when an auction completes."""

    event_type: Literal["pingpost.completed"] = "pingpost.completed"
    lead_id: UUID
    pinged_buyer_ids: list[UUID]
    winning_buyer_id: UUID | None = None
    winning_bid_cents: int | None = None
    duration_ms: int
    rejected_buyers: list[dict[str, str]] = Field(default_factory=list)
    damage_tier: DamageTier | None = None


class CallEvent(_Envelope):
    event_type: Literal[
        "call.started",
        "call.answered",
        "call.no_answer",
        "call.ended",
        "call.transcribed",
        "call.recording_uploaded",
    ]
    call_sid: str
    lead_id: UUID
    direction: Literal["inbound", "outbound"]
    duration_seconds: int | None = None
    recording_s3_key: str | None = None
    transcript_s3_key: str | None = None
