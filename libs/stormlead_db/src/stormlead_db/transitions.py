"""Lead pipeline transition audit helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from stormlead_core import PipelineState, assert_transition

from stormlead_db.tables import LeadStateTransition

ACTIVE_TRANSITION_STATUSES = frozenset({"started"})


@dataclass(frozen=True)
class TransitionWriteResult:
    transition: LeadStateTransition
    inserted: bool


def build_transition_idempotency_key(
    *,
    lead_id: UUID,
    from_state: PipelineState | str | None,
    to_state: PipelineState | str,
    event_type: str,
    task_name: str | None = None,
    version: str = "v1",
) -> str:
    raw = ":".join(
        [
            version,
            str(lead_id),
            str(from_state) if from_state is not None else "start",
            str(to_state),
            event_type,
            task_name or "",
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_transition_by_idempotency_key(
    session: AsyncSession, idempotency_key: str
) -> LeadStateTransition | None:
    return await session.scalar(
        select(LeadStateTransition).where(LeadStateTransition.idempotency_key == idempotency_key)
    )


async def record_transition(
    session: AsyncSession,
    *,
    lead_id: UUID,
    from_state: PipelineState | str | None,
    to_state: PipelineState | str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    task_name: str | None = None,
    workflow_run_id: str | None = None,
    status: str = "succeeded",
) -> TransitionWriteResult:
    if from_state is not None:
        assert_transition(from_state, to_state)
    key = idempotency_key or build_transition_idempotency_key(
        lead_id=lead_id,
        from_state=from_state,
        to_state=to_state,
        event_type=event_type,
        task_name=task_name,
    )
    transition_id = uuid4()
    stmt = (
        pg_insert(LeadStateTransition)
        .values(
            id=transition_id,
            lead_id=lead_id,
            from_state=str(from_state) if from_state is not None else "start",
            to_state=str(to_state),
            event_type=event_type,
            task_name=task_name,
            workflow_run_id=workflow_run_id,
            status=status,
            idempotency_key=key,
            payload_json=payload or {},
        )
        .on_conflict_do_nothing(constraint="uq_lead_state_transitions_idempotency_key")
        .returning(LeadStateTransition)
    )
    try:
        inserted = (await session.execute(stmt)).scalar_one_or_none()
    except IntegrityError:
        inserted = None
    if inserted is not None:
        return TransitionWriteResult(transition=inserted, inserted=True)
    existing = await get_transition_by_idempotency_key(session, key)
    if existing is None:
        raise RuntimeError("transition idempotency conflict without existing transition row")
    return TransitionWriteResult(transition=existing, inserted=False)


async def latest_transition(session: AsyncSession, lead_id: UUID) -> LeadStateTransition | None:
    return await session.scalar(
        select(LeadStateTransition)
        .where(LeadStateTransition.lead_id == lead_id)
        .order_by(LeadStateTransition.created_at.desc())
        .limit(1)
    )


async def latest_state(session: AsyncSession, lead_id: UUID) -> PipelineState | None:
    transition = await latest_transition(session, lead_id)
    return PipelineState(transition.to_state) if transition is not None else None


async def has_active_transition(session: AsyncSession, lead_id: UUID) -> bool:
    active_id = await session.scalar(
        select(LeadStateTransition.id)
        .where(
            LeadStateTransition.lead_id == lead_id,
            LeadStateTransition.status.in_(ACTIVE_TRANSITION_STATUSES),
        )
        .limit(1)
    )
    return active_id is not None
