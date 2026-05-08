from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text
from stormlead_core import get_logger
from stormlead_db import LeadRow, PostResult, get_session

log = get_logger(__name__)


@dataclass(frozen=True)
class CampaignROI:
    campaign_id: str
    leads: int
    leads_sold: int
    leads_returned: int
    revenue_cents: int
    returned_cents: int
    net_revenue_cents: int
    avg_qualification_score: float | None


async def get_campaign_roi(campaign_id: str) -> CampaignROI | None:
    try:
        async with get_session() as session:
            lead_stats = (
                await session.execute(
                    select(
                        func.count(LeadRow.id),
                        func.avg(LeadRow.qualification_score),
                    ).where(LeadRow.campaign_id == campaign_id)
                )
            ).one()
            leads = int(lead_stats[0] or 0)
            if leads == 0:
                return None

            post_stats = (
                await session.execute(
                    select(
                        func.count(PostResult.id).filter(PostResult.delivered.is_(True)),
                        func.count(PostResult.id).filter(PostResult.returned.is_(True)),
                        func.coalesce(
                            func.sum(PostResult.bid_cents).filter(PostResult.delivered.is_(True)), 0
                        ),
                        func.coalesce(
                            func.sum(PostResult.bid_cents).filter(PostResult.returned.is_(True)), 0
                        ),
                    )
                    .join(LeadRow, LeadRow.id == PostResult.lead_id)
                    .where(LeadRow.campaign_id == campaign_id)
                )
            ).one()
    except Exception as exc:
        log.warning("attribution.campaign_roi_failed", campaign_id=campaign_id, error=str(exc))
        return None

    revenue_cents = int(post_stats[2] or 0)
    returned_cents = abs(int(post_stats[3] or 0))
    return CampaignROI(
        campaign_id=campaign_id,
        leads=leads,
        leads_sold=int(post_stats[0] or 0),
        leads_returned=int(post_stats[1] or 0),
        revenue_cents=revenue_cents,
        returned_cents=returned_cents,
        net_revenue_cents=revenue_cents - returned_cents,
        avg_qualification_score=float(lead_stats[1]) if lead_stats[1] is not None else None,
    )


async def get_roi_by_zip(state: str) -> list[dict[str, Any]]:
    sql = text(
        """
        WITH lead_base AS (
            SELECT id, zip, qualification_score
            FROM leads
            WHERE state = :state
        ), post_base AS (
            SELECT
                pr.lead_id,
                COUNT(*) FILTER (WHERE pr.delivered IS TRUE) AS sold,
                COUNT(*) FILTER (WHERE pr.returned IS TRUE) AS returned,
                COALESCE(SUM(pr.bid_cents) FILTER (WHERE pr.delivered IS TRUE), 0) AS revenue_cents,
                COALESCE(SUM(pr.bid_cents) FILTER (WHERE pr.returned IS TRUE), 0) AS returned_cents
            FROM post_results pr
            JOIN lead_base lb ON lb.id = pr.lead_id
            GROUP BY pr.lead_id
        )
        SELECT
            lb.zip,
            COUNT(lb.id) AS leads,
            COALESCE(SUM(pb.sold), 0) AS leads_sold,
            COALESCE(SUM(pb.returned), 0) AS leads_returned,
            COALESCE(SUM(pb.revenue_cents), 0) AS revenue_cents,
            ABS(COALESCE(SUM(pb.returned_cents), 0)) AS returned_cents,
            AVG(lb.qualification_score) AS avg_qualification_score
        FROM lead_base lb
        LEFT JOIN post_base pb ON pb.lead_id = lb.id
        GROUP BY lb.zip
        ORDER BY revenue_cents DESC, leads DESC
        LIMIT 50
        """
    )
    try:
        async with get_session() as session:
            result = await session.execute(sql, {"state": state.upper()})
            rows = result.mappings().all()
    except Exception as exc:
        log.warning("attribution.roi_by_zip_failed", state=state, error=str(exc))
        return []

    output: list[dict[str, Any]] = []
    for row in rows:
        revenue_cents = int(row["revenue_cents"] or 0)
        returned_cents = int(row["returned_cents"] or 0)
        output.append(
            {
                "zip": row["zip"],
                "leads": int(row["leads"] or 0),
                "leads_sold": int(row["leads_sold"] or 0),
                "leads_returned": int(row["leads_returned"] or 0),
                "revenue_cents": revenue_cents,
                "returned_cents": returned_cents,
                "net_revenue_cents": revenue_cents - returned_cents,
                "avg_qualification_score": float(row["avg_qualification_score"])
                if row["avg_qualification_score"] is not None
                else None,
            }
        )
    return output
