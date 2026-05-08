from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from stormlead_db import CallEventRow, LeadRow

from form_receiver.schemas import CallOutcome


class CallTrackingEvent(BaseModel):
    call_id: str = Field(min_length=1, max_length=128)
    phone_e164: str = Field(min_length=8, max_length=20)
    duration_seconds: int | None = Field(default=None, ge=0)
    outcome: CallOutcome
    tracked_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)


async def ingest_call_event(event: CallTrackingEvent, session: AsyncSession) -> dict[str, Any]:
    lead_id = (
        await session.execute(
            select(LeadRow.id)
            .where(LeadRow.phone_e164 == event.phone_e164)
            .order_by(desc(LeadRow.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    raw_payload = event.raw_payload or event.model_dump(mode="json")
    stmt = (
        pg_insert(CallEventRow)
        .values(
            call_id=event.call_id,
            lead_id=lead_id,
            phone_e164=event.phone_e164,
            duration_seconds=event.duration_seconds,
            outcome=event.outcome.value,
            tracked_at=event.tracked_at,
            raw_payload=raw_payload,
        )
        .on_conflict_do_update(
            index_elements=["call_id"],
            set_={
                "lead_id": lead_id,
                "duration_seconds": event.duration_seconds,
                "outcome": event.outcome.value,
                "tracked_at": event.tracked_at,
                "raw_payload": raw_payload,
            },
        )
        .returning(CallEventRow.id, CallEventRow.lead_id)
    )
    row = (await session.execute(stmt)).one()
    return {
        "call_id": event.call_id,
        "event_id": str(row.id),
        "lead_id": str(row.lead_id) if row.lead_id else None,
        "matched": row.lead_id is not None,
    }
