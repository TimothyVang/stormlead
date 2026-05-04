"""Replay planning for lead pipeline recovery."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from stormlead_core.pipeline import PipelineState


@dataclass(frozen=True)
class ReplayPlan:
    lead_id: UUID
    from_state: PipelineState | None
    event_name: str | None
    reason: str
    executable: bool


_STATE_TO_EVENT: dict[PipelineState | None, str] = {
    None: "lead.captured",
    PipelineState.CAPTURED: "lead.captured",
    PipelineState.ENRICHED: "lead.enriched",
    PipelineState.QUALIFIED: "lead.qualified",
    PipelineState.UNSOLD: "lead.unsold",
    PipelineState.REJECTED: "lead.rejected",
}


def build_replay_plan(lead_id: UUID, from_state: PipelineState | None) -> ReplayPlan:
    if from_state == PipelineState.SOLD:
        return ReplayPlan(
            lead_id=lead_id,
            from_state=from_state,
            event_name=None,
            reason="sold leads are terminal; choose an earlier FROM_STATE to replay",
            executable=False,
        )
    if from_state == PipelineState.NURTURED:
        return ReplayPlan(
            lead_id=lead_id,
            from_state=from_state,
            event_name=None,
            reason="nurtured leads are terminal; choose an earlier FROM_STATE to replay",
            executable=False,
        )
    event_name = _STATE_TO_EVENT.get(from_state)
    if event_name is None:
        return ReplayPlan(
            lead_id=lead_id,
            from_state=from_state,
            event_name=None,
            reason=f"no replay event is defined for state {from_state}",
            executable=False,
        )
    return ReplayPlan(
        lead_id=lead_id,
        from_state=from_state,
        event_name=event_name,
        reason=f"re-enqueue {event_name} from checkpoint {from_state.value if from_state else 'start'}",
        executable=True,
    )
