from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from hatchet_sdk import Hatchet
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from stormlead_core import (
    PipelineState,
    build_duplicate_window,
    get_logger,
    initial_quality_score,
)
from stormlead_db import ConsentAudit, LeadRow, SuppressionEntry, get_session, record_transition

from form_receiver.schemas import ExtractedConsent

log = get_logger(__name__)


class SuppressedLeadError(ValueError):
    """Raised when a captured lead matches an active opt-out entry."""

    def __init__(self, suppression_id: UUID, reason: str) -> None:
        super().__init__("lead matches an active suppression entry")
        self.suppression_id = suppression_id
        self.reason = reason


async def upsert_lead(extracted: ExtractedConsent, *, ip: str) -> UUID:
    page_html_hash = extracted.page_html_sha256 or ""
    new_id = uuid4()
    now = datetime.now(UTC)
    duplicate_hours = int(os.getenv("LEAD_DUPLICATE_WINDOW_HOURS", "72"))
    dedup = build_duplicate_window(
        phone=extracted.phone_e164,
        address_line1=extracted.address_line1,
        city=extracted.city,
        state=extracted.state,
        zip_code=extracted.zip,
        storm_id=None,
        submitted_at=now,
        lookback_hours=duplicate_hours,
    )

    async with get_session() as s:
        suppression_clauses = [SuppressionEntry.phone_e164 == extracted.phone_e164]
        if extracted.email:
            suppression_clauses.append(SuppressionEntry.email == extracted.email)
        suppression = (
            (
                await s.execute(
                    select(SuppressionEntry).where(
                        SuppressionEntry.status == "active",
                        or_(*suppression_clauses),
                    )
                )
            )
            .scalars()
            .first()
        )
        if suppression is not None:
            raise SuppressedLeadError(suppression.id, suppression.reason)

        dup_exists = (
            await s.execute(
                select(LeadRow.id).where(
                    LeadRow.phone_e164 == extracted.phone_e164,
                    LeadRow.created_at >= dedup.window_start,
                    or_(
                        LeadRow.storm_id.is_(None),
                        LeadRow.storm_id == dedup.storm_id,
                    ),
                )
            )
        ).first() is not None
        score = initial_quality_score(
            dwell_ms=extracted.dwell_ms,
            has_email=bool(extracted.email),
            duplicate=dup_exists,
        )

        stmt = (
            pg_insert(LeadRow)
            .values(
                id=new_id,
                source="landing_form",
                status="new",
                name=extracted.name,
                phone_e164=extracted.phone_e164,
                email=extracted.email,
                address_line1=extracted.address_line1,
                city=extracted.city,
                state=extracted.state,
                zip=extracted.zip,
                consent_text=extracted.consent_text,
                consent_ip=ip,
                consent_user_agent=extracted.user_agent,
                consent_at=now,
                page_url=extracted.page_url,
                page_html_hash=page_html_hash,
                score=score.score,
                score_reason=score.reason,
                hold_for_review=score.hold,
                blocked_for_fraud=score.blocked,
                requested_service=extracted.requested_service,
                campaign_id=extracted.campaign_id,
                campaign_source=extracted.campaign_source,
                first_touch_source=extracted.first_touch_source,
                last_touch_source=extracted.last_touch_source,
            )
            .on_conflict_do_nothing(constraint="uq_lead_phone_hash")
            .returning(LeadRow.id)
        )
        result = (await s.execute(stmt)).first()
        if result is not None:
            await record_transition(
                s,
                lead_id=result.id,
                from_state=None,
                to_state=PipelineState.CAPTURED,
                event_type="lead.captured",
                task_name="form_receiver.upsert_lead",
                payload={
                    "source": "landing_form",
                    "webhook_id": extracted.formbricks_response_id,
                    "requested_service": extracted.requested_service,
                    "campaign_id": extracted.campaign_id,
                    "campaign_source": extracted.campaign_source,
                },
            )
            return result.id

        existing = (
            await s.execute(
                select(LeadRow.id).where(
                    LeadRow.phone_e164 == extracted.phone_e164,
                    LeadRow.page_html_hash == page_html_hash,
                )
            )
        ).first()
        if existing is None:
            raise RuntimeError("lead conflict but no existing row found")
        return existing.id


async def record_audit(
    *, webhook_id: str, lead_id: UUID, extracted: ExtractedConsent, ip: str, raw_payload: bytes
) -> bool:
    parsed_payload = json.loads(raw_payload.decode("utf-8"))
    async with get_session() as s:
        stmt = (
            pg_insert(ConsentAudit)
            .values(
                webhook_id=webhook_id,
                lead_id=lead_id,
                formbricks_response_id=extracted.formbricks_response_id,
                page_url=extracted.page_url,
                ip=ip,
                user_agent=extracted.user_agent,
                consent_text=extracted.consent_text,
                page_html_sha256=extracted.page_html_sha256,
                dwell_ms=extracted.dwell_ms,
                raw_payload=parsed_payload,
            )
            .on_conflict_do_nothing(index_elements=["webhook_id"])
            .returning(ConsentAudit.webhook_id)
        )
        result = (await s.execute(stmt)).first()
    return result is not None


async def record_suppression(
    *, phone_e164: str | None, email: str | None, reason: str, source: str
) -> tuple[UUID, bool]:
    async with get_session() as s:
        clauses = []
        if phone_e164:
            clauses.append(SuppressionEntry.phone_e164 == phone_e164)
        if email:
            clauses.append(SuppressionEntry.email == email)
        existing = None
        if clauses:
            existing = (
                (
                    await s.execute(
                        select(SuppressionEntry).where(
                            SuppressionEntry.status == "active",
                            or_(*clauses),
                        )
                    )
                )
                .scalars()
                .first()
            )
        if existing is not None:
            return existing.id, False

        row = SuppressionEntry(
            phone_e164=phone_e164,
            email=email,
            reason=reason,
            source=source,
            metadata_json={},
        )
        s.add(row)
        await s.flush()
        return row.id, True


async def emit_lead_captured(hatchet: Hatchet, lead_id: UUID) -> None:
    payload = {"lead_id": str(lead_id)}
    hatchet.event.push("lead.captured", payload)
    log.info("event.pushed", hatchet_event="lead.captured", lead_id=str(lead_id))
