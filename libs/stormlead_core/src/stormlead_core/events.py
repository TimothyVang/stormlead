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
from typing import Any, Literal
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


class AgentTaskEnvelope(BaseModel):
    """canonical envelope for auditable agent task execution."""

    task_name: str
    workflow_name: str
    run_id: str
    input_payload: dict[str, Any]
    correlation_id: UUID | None = None
    timeout_seconds: int
    retry_count: int
    model_tier: Literal["premium", "standard", "economy"]
    primary_model: str
    fallback_model: str | None = None
    token_cap: int
    cost_cap_usd: float


class AgentTaskEvent(_Envelope):
    """structured lifecycle events for runtime observability."""

    event_type: Literal[
        "agent.task.started",
        "agent.task.succeeded",
        "agent.task.failed",
        "agent.task.dead_lettered",
    ]
    task: AgentTaskEnvelope
    status: Literal["started", "success", "failure", "dead_lettered"]
    attempt: int
    model_used: str
    fallback_used: bool = False
    duration_ms: int | None = None
    error: str | None = None
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    estimated_cost_usd: float | None = None


class AgentRunEvent(_Envelope):
    """run-level workflow lifecycle for visual agentic orchestration."""

    event_type: Literal[
        "run.started",
        "step.started",
        "step.succeeded",
        "step.failed",
        "run.awaiting_approval",
        "run.completed",
        "run.failed",
        "run.canceled",
    ]
    run_id: str
    lead_id: UUID | None = None
    step_id: UUID | None = None
    step_type: str | None = None
    status: Literal["queued", "running", "awaiting_approval", "completed", "failed", "canceled"]
    attempt: int = 1
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
