from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID, uuid4

from hatchet_sdk import Hatchet
from sqlalchemy import and_, func, or_, select, update
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


class DuplicateLeadError(ValueError):
    """Raised when a new capture matches a recent lead duplicate window."""

    def __init__(self, duplicate_lead_id: UUID, reason: str, window_hours: int) -> None:
        super().__init__("lead matches a recent duplicate window")
        self.duplicate_lead_id = duplicate_lead_id
        self.reason = reason
        self.window_hours = window_hours


class CaptureWebhookStatus(NamedTuple):
    lead_id: UUID
    event_status: str
    audit_recorded: bool

    @property
    def event_emitted(self) -> bool:
        return self.event_status == "sent"


async def upsert_lead(
    extracted: ExtractedConsent, *, ip: str, webhook_id: str | None = None
) -> tuple[UUID, bool]:
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
        if webhook_id:
            existing_capture = (
                await s.execute(select(LeadRow.id).where(LeadRow.capture_webhook_id == webhook_id))
            ).first()
            if existing_capture is not None:
                return existing_capture.id, False

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

        lock_key = "|".join(
            [
                extracted.phone_e164,
                dedup.address_norm,
                str(dedup.storm_id or ""),
            ]
        )
        await s.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_key))))
        if webhook_id:
            existing_capture = (
                await s.execute(select(LeadRow.id).where(LeadRow.capture_webhook_id == webhook_id))
            ).first()
            if existing_capture is not None:
                return existing_capture.id, False

        same_contact_address_storm = [
            LeadRow.phone_e164 == extracted.phone_e164,
            LeadRow.normalized_address == dedup.address_norm,
        ]
        if dedup.storm_id is not None:
            same_contact_address_storm.append(
                or_(
                    LeadRow.storm_id.is_(None),
                    LeadRow.storm_id == dedup.storm_id,
                )
            )
        duplicate = (
            await s.execute(
                select(LeadRow.id)
                .where(
                    *same_contact_address_storm,
                    LeadRow.created_at >= dedup.window_start,
                )
                .order_by(LeadRow.created_at.desc())
                .limit(1)
            )
        ).first()
        if duplicate is not None:
            raise DuplicateLeadError(
                duplicate.id,
                reason="duplicate_window_match",
                window_hours=duplicate_hours,
            )

        resale_exists = (
            await s.execute(select(LeadRow.id).where(*same_contact_address_storm).limit(1))
        ).first() is not None
        is_resale = resale_exists
        score = initial_quality_score(
            dwell_ms=extracted.dwell_ms,
            has_email=bool(extracted.email),
            duplicate=is_resale,
            photo_count=len(extracted.photo_s3_keys),
            location_verified=extracted.location_verification_status == "verified",
            urgency=extracted.urgency,
            safety_flags=extracted.safety_flags,
        )

        stmt = (
            pg_insert(LeadRow)
            .values(
                id=new_id,
                source="landing_form",
                status="new",
                capture_webhook_id=webhook_id,
                name=extracted.name,
                phone_e164=extracted.phone_e164,
                email=extracted.email,
                address_line1=extracted.address_line1,
                city=extracted.city,
                state=extracted.state,
                zip=extracted.zip,
                normalized_address=dedup.address_norm,
                damage_description=extracted.damage_description,
                damage_type=extracted.damage_type,
                urgency=extracted.urgency,
                safety_flags=extracted.safety_flags,
                consent_text=extracted.consent_text,
                consent_version=extracted.consent_version,
                consent_ip=ip,
                consent_user_agent=extracted.user_agent,
                consent_at=now,
                page_url=extracted.page_url,
                page_html_hash=page_html_hash,
                trustedform_cert_url=extracted.trustedform_cert_url,
                photo_s3_keys=extracted.photo_s3_keys,
                google_click_id=extracted.google_click_id,
                gps_latitude=extracted.gps_latitude,
                gps_longitude=extracted.gps_longitude,
                gps_accuracy_meters=extracted.gps_accuracy_meters,
                gps_captured_at=extracted.gps_captured_at,
                location_source=extracted.location_source,
                location_confirmed_at=extracted.location_confirmed_at,
                location_verification_status=extracted.location_verification_status,
                score=score.score,
                score_reason=score.reason,
                hold_for_review=score.hold,
                blocked_for_fraud=score.blocked,
                is_resale=is_resale,
                lead_class="d" if is_resale else None,
                requested_service=extracted.requested_service,
                campaign_id=extracted.campaign_id,
                campaign_source=extracted.campaign_source,
                first_touch_source=extracted.first_touch_source,
                last_touch_source=extracted.last_touch_source,
            )
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
                    "webhook_id": webhook_id,
                    "formbricks_response_id": extracted.formbricks_response_id,
                    "requested_service": extracted.requested_service,
                    "damage_type": extracted.damage_type,
                    "urgency": extracted.urgency,
                    "safety_flags": extracted.safety_flags,
                    "campaign_id": extracted.campaign_id,
                    "campaign_source": extracted.campaign_source,
                    "google_click_id_present": bool(extracted.google_click_id),
                    "location_verification_status": extracted.location_verification_status,
                    "gps_accuracy_meters": extracted.gps_accuracy_meters,
                    "photo_count": len(extracted.photo_s3_keys),
                    "trustedform_cert_url_present": bool(extracted.trustedform_cert_url),
                    "consent_version": extracted.consent_version,
                },
            )
            return result.id, True

        raise RuntimeError("lead conflict but no existing row found")


async def capture_status_for_webhook(webhook_id: str) -> CaptureWebhookStatus | None:
    async with get_session() as s:
        lead_row = (
            await s.execute(
                select(
                    LeadRow.id,
                    LeadRow.capture_event_emitted_at,
                    LeadRow.capture_event_status,
                ).where(LeadRow.capture_webhook_id == webhook_id)
            )
        ).first()
        if lead_row is not None:
            audit_recorded = (
                await s.scalar(
                    select(ConsentAudit.webhook_id).where(ConsentAudit.webhook_id == webhook_id)
                )
            ) is not None
            return CaptureWebhookStatus(
                lead_id=lead_row.id,
                event_status="sent"
                if lead_row.capture_event_emitted_at is not None
                else lead_row.capture_event_status,
                audit_recorded=audit_recorded,
            )

        audit_lead_id = await s.scalar(
            select(ConsentAudit.lead_id).where(ConsentAudit.webhook_id == webhook_id)
        )
        if audit_lead_id is None:
            return None
        event_row = (
            await s.execute(
                select(LeadRow.capture_event_emitted_at, LeadRow.capture_event_status).where(
                    LeadRow.id == audit_lead_id
                )
            )
        ).first()
        return CaptureWebhookStatus(
            lead_id=audit_lead_id,
            event_status="sent"
            if event_row is not None and event_row.capture_event_emitted_at is not None
            else (event_row.capture_event_status if event_row is not None else "pending"),
            audit_recorded=True,
        )


async def claim_capture_event_dispatch(lead_id: UUID) -> bool:
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=5)
    async with get_session() as s:
        result = await s.execute(
            update(LeadRow)
            .where(
                LeadRow.id == lead_id,
                or_(
                    LeadRow.capture_event_status.in_(["pending", "failed"]),
                    LeadRow.capture_event_status.is_(None),
                    and_(
                        LeadRow.capture_event_status == "sending",
                        LeadRow.capture_event_claimed_at < stale_before,
                    ),
                ),
            )
            .values(capture_event_status="sending", capture_event_claimed_at=now)
        )
        return getattr(result, "rowcount", 0) == 1


async def mark_capture_event_emitted(lead_id: UUID) -> None:
    async with get_session() as s:
        await s.execute(
            update(LeadRow)
            .where(LeadRow.id == lead_id)
            .values(
                capture_event_status="sent",
                capture_event_emitted_at=datetime.now(UTC),
                capture_event_claimed_at=None,
            )
        )


async def mark_capture_event_failed(lead_id: UUID) -> None:
    async with get_session() as s:
        await s.execute(
            update(LeadRow)
            .where(LeadRow.id == lead_id)
            .values(capture_event_status="failed", capture_event_claimed_at=None)
        )


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
                consent_version=extracted.consent_version,
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
    if phone_e164 is None and email is None:
        raise ValueError("suppression requires phone or email")

    new_id = uuid4()
    async with get_session() as s:
        stmt = (
            pg_insert(SuppressionEntry)
            .values(
                id=new_id,
                phone_e164=phone_e164,
                email=email,
                reason=reason,
                source=source,
                metadata_json={},
            )
            .on_conflict_do_nothing()
            .returning(SuppressionEntry.id)
        )
        result = (await s.execute(stmt)).first()
        if result is not None:
            return result.id, True

        clauses = []
        if phone_e164:
            clauses.append(SuppressionEntry.phone_e164 == phone_e164)
        if email:
            clauses.append(SuppressionEntry.email == email)
        existing = (
            (await s.execute(select(SuppressionEntry).where(or_(*clauses)))).scalars().first()
        )
        if existing is not None:
            if existing.status != "active":
                await s.execute(
                    update(SuppressionEntry)
                    .where(SuppressionEntry.id == existing.id)
                    .values(
                        status="active",
                        reason=reason,
                        source=source,
                        updated_at=datetime.now(UTC),
                    )
                )
            return existing.id, False
        raise RuntimeError("suppression conflict but no existing row found")


async def emit_lead_captured(hatchet: Hatchet, lead_id: UUID) -> None:
    payload = {"lead_id": str(lead_id), "idempotency_key": f"lead.captured:{lead_id}"}
    hatchet.event.push("lead.captured", payload)
    log.info("event.pushed", hatchet_event="lead.captured", lead_id=str(lead_id))
