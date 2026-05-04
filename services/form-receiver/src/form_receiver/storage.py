"""persist a captured lead + consent audit, then emit lead.captured.

dedup: the standard-webhooks `webhook-id` header is the primary key on
consent_audits. ON CONFLICT DO NOTHING + a returning-count check tells
us whether the delivery was new (→ emit hatchet event) or a retry
(→ no-op, return success).

lead-level dedup: LeadRow has UniqueConstraint(phone_e164, page_html_hash).
same homeowner re-submitting the same page → same lead row reused.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from hatchet_sdk import Hatchet
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from stormlead_core import get_logger
from stormlead_db import ConsentAudit, LeadRow, get_session

from form_receiver.schemas import ExtractedConsent

log = get_logger(__name__)


async def upsert_lead(extracted: ExtractedConsent, *, ip: str) -> UUID:
    """upsert by (phone_e164, page_html_hash). returns the lead id (new or existing)."""
    page_html_hash = extracted.page_html_sha256 or ""  # column is non-null
    new_id = uuid4()
    now = datetime.now(UTC)

    async with get_session() as s:
        # try insert; on conflict (phone, hash), do nothing
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
            return result.id

        # conflict: fetch the existing row
        existing = (
            await s.execute(
                select(LeadRow.id).where(
                    LeadRow.phone_e164 == extracted.phone_e164,
                    LeadRow.page_html_hash == page_html_hash,
                )
            )
        ).first()
        if existing is None:
            # shouldn't happen — we just hit the unique constraint
            raise RuntimeError("lead conflict but no existing row found")
        return existing.id


async def record_audit(
    *,
    webhook_id: str,
    lead_id: UUID,
    extracted: ExtractedConsent,
    ip: str,
    raw_payload: bytes,
) -> bool:
    """write a consent_audits row keyed on webhook_id. returns True if new, False if dup."""
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


async def emit_lead_captured(hatchet: Hatchet, lead_id: UUID) -> None:
    """push the hatchet event that agent-runtime's QualifyLead workflow listens for."""
    payload = {"lead_id": str(lead_id)}
    # hatchet-sdk's event push api: client.event.push(event_key, payload)
    hatchet.event.push("lead.captured", payload)
    # structlog's `event` positional means the log message; using it again
    # as a kwarg collides. rename to `hatchet_event` for the payload-name field.
    log.info("event.pushed", hatchet_event="lead.captured", lead_id=str(lead_id))
