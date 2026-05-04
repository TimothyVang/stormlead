from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stormlead_db.tables import BillingEvent, BuyerRow, PostResult


FAIL_INSUFFICIENT_BALANCE_AT_POST = "INSUFFICIENT_BALANCE_AT_POST"
FAIL_BUYER_PAUSED_AFTER_PING = "BUYER_PAUSED_AFTER_PING"
FAIL_CAP_REACHED_AT_POST = "CAP_REACHED_AT_POST"


@dataclass
class PostFinalizeResult:
    delivered: bool
    failure_reason: str | None
    duplicated: bool = False


async def finalize_post_attempt(
    s: AsyncSession,
    *,
    lead_id: UUID,
    buyer_id: UUID,
    bid_cents: int,
    post_attempt_key: str,
    delivery_ok: bool,
    response_status_code: int | None,
    response_body: str | None,
) -> PostFinalizeResult:
    existing = await s.scalar(select(PostResult).where(PostResult.post_attempt_key == post_attempt_key))
    if existing:
        return PostFinalizeResult(
            delivered=existing.delivered,
            failure_reason=existing.return_reason,
            duplicated=True,
        )

    buyer = await s.scalar(select(BuyerRow).where(BuyerRow.id == buyer_id).with_for_update())
    if buyer is None:
        s.add(
            PostResult(
                lead_id=lead_id,
                buyer_id=buyer_id,
                bid_cents=bid_cents,
                post_attempt_key=post_attempt_key,
                delivered=False,
                response_status_code=response_status_code,
                response_body=response_body,
                return_reason=FAIL_BUYER_PAUSED_AFTER_PING,
            )
        )
        return PostFinalizeResult(delivered=False, failure_reason=FAIL_BUYER_PAUSED_AFTER_PING)

    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day_count = await s.scalar(
        select(func.count(PostResult.id)).where(
            PostResult.buyer_id == buyer_id,
            PostResult.delivered.is_(True),
            PostResult.created_at >= day_start,
        )
    )
    month_spend_cents = await s.scalar(
        select(func.coalesce(func.sum(PostResult.bid_cents), 0)).where(
            PostResult.buyer_id == buyer_id,
            PostResult.delivered.is_(True),
            PostResult.created_at >= month_start,
        )
    )

    failure_reason = None
    debit = Decimal(bid_cents) / Decimal(100)
    if buyer.status != "active":
        failure_reason = FAIL_BUYER_PAUSED_AFTER_PING
    elif buyer.deposit_balance < debit:
        failure_reason = FAIL_INSUFFICIENT_BALANCE_AT_POST
    elif (day_count or 0) >= buyer.daily_cap:
        failure_reason = FAIL_CAP_REACHED_AT_POST
    elif (Decimal(int(month_spend_cents or 0)) + Decimal(bid_cents)) / Decimal(100) > buyer.monthly_budget:
        failure_reason = FAIL_CAP_REACHED_AT_POST

    delivered = bool(delivery_ok and failure_reason is None)

    if delivered:
        buyer.deposit_balance -= debit
        buyer.lifetime_spend += debit
        s.add(
            BillingEvent(
                buyer_id=buyer_id,
                lead_id=lead_id,
                event_type="lead.reserved",
                amount_cents=-bid_cents,
                metadata_json={"exclusive": True, "post_attempt_key": post_attempt_key},
            )
        )

    s.add(
        PostResult(
            lead_id=lead_id,
            buyer_id=buyer_id,
            bid_cents=bid_cents,
            post_attempt_key=post_attempt_key,
            delivered=delivered,
            response_status_code=response_status_code,
            response_body=response_body,
            return_reason=failure_reason,
        )
    )

    return PostFinalizeResult(delivered=delivered, failure_reason=failure_reason)
