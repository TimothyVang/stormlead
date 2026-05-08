from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from stormlead_core import get_logger
from stormlead_db import BuyerRow, PingAttempt, PostResult, ReturnRequest, get_session

log = get_logger(__name__)

ADJUSTMENT_RATE_THRESHOLD = 0.25
AVG_PING_RESPONSE_MS_THRESHOLD = 600_000


def _commercial_guardrails_enabled() -> bool:
    return os.getenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "false").lower() == "true"


async def _adjustment_rate(session: AsyncSession, buyer_id: UUID) -> float:
    total = await session.scalar(
        select(func.count(PostResult.id)).where(
            PostResult.buyer_id == buyer_id,
            PostResult.delivered.is_(True),
        )
    )
    if not total:
        return 0.0
    returned = await session.scalar(
        select(func.count(ReturnRequest.id)).where(
            ReturnRequest.buyer_id == buyer_id,
            ReturnRequest.status == "approved",
        )
    )
    return float(returned or 0) / float(total)


async def _avg_ping_response_ms(session: AsyncSession, buyer_id: UUID) -> float:
    avg = await session.scalar(
        select(func.avg(PingAttempt.response_ms)).where(
            PingAttempt.buyer_id == buyer_id,
            PingAttempt.response_ms.is_not(None),
        )
    )
    return float(avg or 0)


async def evaluate_buyer_guardrails() -> list[dict[str, Any]]:
    if not _commercial_guardrails_enabled():
        return []

    actions: list[dict[str, Any]] = []
    async with get_session() as session:
        buyers = (
            (
                await session.execute(
                    select(BuyerRow.id, BuyerRow.company).where(BuyerRow.status == "active")
                )
            )
            .all()
        )
        for buyer_id, company in buyers:
            reasons = []
            adjustment_rate = await _adjustment_rate(session, buyer_id)
            avg_ping_ms = await _avg_ping_response_ms(session, buyer_id)
            if adjustment_rate > ADJUSTMENT_RATE_THRESHOLD:
                reasons.append("adjustment_rate")
            if avg_ping_ms > AVG_PING_RESPONSE_MS_THRESHOLD:
                reasons.append("avg_ping_response_ms")
            if not reasons:
                continue

            await session.execute(
                update(BuyerRow).where(BuyerRow.id == buyer_id).values(status="paused")
            )
            action = {
                "buyer_id": str(buyer_id),
                "company": company,
                "action": "paused",
                "reasons": reasons,
                "adjustment_rate": adjustment_rate,
                "avg_ping_response_ms": avg_ping_ms,
            }
            log.warning("guardrails.buyer_paused", **action)
            actions.append(action)
    return actions
