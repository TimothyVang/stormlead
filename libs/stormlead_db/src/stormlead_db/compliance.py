from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select

from stormlead_db import get_session
from stormlead_db.tables import DncEntryRow, SuppressionEntryRow


@dataclass(frozen=True)
class SuppressionLookupResult:
    blocked: bool
    rule: str | None = None
    source: str | None = None


async def lookup_suppression(phone_e164: str, email: str | None = None) -> SuppressionLookupResult:
    async with get_session() as s:
        row = await s.scalar(
            select(SuppressionEntryRow)
            .where(SuppressionEntryRow.active.is_(True))
            .where(
                or_(
                    SuppressionEntryRow.phone_e164 == phone_e164,
                    SuppressionEntryRow.email == email if email else False,
                )
            )
            .limit(1)
        )
    if row is None:
        return SuppressionLookupResult(blocked=False)
    return SuppressionLookupResult(blocked=True, rule="suppression_list", source=row.source)


async def lookup_dnc(phone_e164: str, at: datetime | None = None) -> SuppressionLookupResult:
    now = at or datetime.utcnow()
    async with get_session() as s:
        row = await s.scalar(
            select(DncEntryRow)
            .where(DncEntryRow.phone_e164 == phone_e164)
            .where(DncEntryRow.active.is_(True))
            .where(or_(DncEntryRow.expires_at.is_(None), DncEntryRow.expires_at > now))
            .limit(1)
        )
    if row is None:
        return SuppressionLookupResult(blocked=False)
    return SuppressionLookupResult(blocked=True, rule="dnc_list", source=row.source)


async def record_compliance_decision_log(
    *,
    actor: str,
    action: str,
    lead_id: UUID | None,
    buyer_id: UUID | None,
    blocked: bool,
    rule_hit: str | None,
    details: dict,
) -> None:
    from stormlead_db.tables import ComplianceDecisionLogRow

    async with get_session() as s:
        s.add(
            ComplianceDecisionLogRow(
                actor=actor,
                action=action,
                lead_id=lead_id,
                buyer_id=buyer_id,
                blocked=blocked,
                rule_hit=rule_hit,
                details_json=details,
            )
        )
