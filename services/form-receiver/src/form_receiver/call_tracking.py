from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from stormlead_core import is_production
from stormlead_db import CallEventRow, LeadRow

from form_receiver.schemas import CallOutcome
from form_receiver.signatures import InvalidSignatureError, MissingHeaderError, ReplayError

CALL_TRACKING_REPLAY_WINDOW_S = 5 * 60


class CallTrackingEvent(BaseModel):
    call_id: str = Field(min_length=1, max_length=128)
    phone_e164: str = Field(min_length=8, max_length=20)
    duration_seconds: int | None = Field(default=None, ge=0)
    outcome: CallOutcome
    tracked_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)


def verify_call_tracking_signature(
    *,
    raw_body: bytes,
    signature: str | None,
    timestamp: str | None,
    secret: str,
    now_unix: int | None = None,
) -> None:
    """Verify call-tracking webhook HMAC over `<timestamp>.<raw_body>`."""
    if not secret:
        if is_production():
            raise InvalidSignatureError("CALL_TRACKING_WEBHOOK_SECRET is required in production")
        return
    if not signature or not timestamp:
        raise MissingHeaderError("missing call-tracking signature headers")

    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise MissingHeaderError("invalid call-tracking timestamp") from exc

    now = now_unix if now_unix is not None else int(time.time())
    if abs(now - ts) > CALL_TRACKING_REPLAY_WINDOW_S:
        raise ReplayError(f"timestamp outside ±{CALL_TRACKING_REPLAY_WINDOW_S}s window")

    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    candidates = [part.split(",", 1)[1] for part in signature.split(" ") if part.startswith("v1,")]
    if not candidates:
        candidates = [signature]

    matched = False
    for candidate in candidates:
        if hmac.compare_digest(candidate, expected):
            matched = True
    if not matched:
        raise InvalidSignatureError("call-tracking signature mismatch")


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
