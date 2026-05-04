"""agent-runtime hatchet worker entrypoint."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from hatchet_sdk import Context, Hatchet
from sqlalchemy import desc, func, select
from stormlead_core import BuyerSalesStage, BuyerStatus, configure_logging, get_logger
from stormlead_db import BuyerRow, CampaignDecisionRow, LeadRow, StormRow, get_session

from agent_runtime.hermes import hermes_self_evolution
from agent_runtime.qualify import qualify_lead

configure_logging()
log = get_logger(__name__)

hatchet = Hatchet(debug=False)

MIN_FUNDED_BUYERS = 2
MIN_WALLET_RUNWAY_USD = Decimal("1500")
MAX_ALLOWABLE_CPL_USD = Decimal("120")
BUYER_RESPONSE_SLA_MS = 1500


class DecisionState(StrEnum):
    HOLD = "HOLD"
    LAUNCH = "LAUNCH"
    SCALE = "SCALE"
    PAUSE = "PAUSE"
    STOP_LOSS = "STOP_LOSS"


async def run_campaign_orchestrator(_: Context) -> dict[str, Any]:
    metrics = await _collect_metrics_snapshot()
    decision_state, reasons = _decide_state(metrics)

    async with get_session() as s:
        record = CampaignDecisionRow(
            market_key=metrics["market_key"],
            decision_state=decision_state.value,
            reason_codes=reasons,
            metrics_snapshot=metrics,
            spend_blocked=decision_state in {DecisionState.PAUSE, DecisionState.STOP_LOSS},
        )
        s.add(record)
        await s.commit()

    if decision_state in {DecisionState.PAUSE, DecisionState.STOP_LOSS}:
        hatchet.event.push(
            "campaign.spend_blocked",
            {"market_key": metrics["market_key"], "state": decision_state.value, "reasons": reasons},
        )

    return {"state": decision_state.value, "reasons": reasons, "metrics": metrics}


async def _collect_metrics_snapshot() -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(hours=24)
    async with get_session() as s:
        severity = await s.scalar(
            select(StormRow.severity)
            .where(StormRow.detected_at >= since)
            .order_by(desc(StormRow.detected_at))
            .limit(1)
        )

        funded_q = select(BuyerRow).where(
            BuyerRow.status == BuyerStatus.ACTIVE.value,
            BuyerRow.sales_stage == BuyerSalesStage.FUNDED.value,
        )
        funded = (await s.execute(funded_q)).scalars().all()
        funded_buyers = len(funded)
        wallet_runway = sum((buyer.deposit_balance for buyer in funded), Decimal("0"))
        zip_coverage = len({zip_code for buyer in funded for zip_code in (buyer.target_zips or [])})

        avg_cpl = await s.scalar(
            select(func.avg(BuyerRow.bid_per_lead_t1_t2)).where(
                BuyerRow.status == BuyerStatus.ACTIVE.value,
                BuyerRow.sales_stage == BuyerSalesStage.FUNDED.value,
            )
        )
        avg_response_ms = await s.scalar(
            select(func.avg(LeadRow.qualification_score)).where(LeadRow.created_at >= since)
        )

    return {
        "market_key": "US",
        "storm_severity": severity or "none",
        "funded_buyers": funded_buyers,
        "wallet_runway_usd": float(wallet_runway),
        "zip_coverage_count": zip_coverage,
        "cap_headroom": float(wallet_runway / max(funded_buyers, 1)),
        "avg_cpl_usd": float(avg_cpl or 0),
        "buyer_response_sla_ms": int(avg_response_ms or 0),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _decide_state(metrics: dict[str, Any]) -> tuple[DecisionState, list[str]]:
    reasons: list[str] = []
    severity = str(metrics["storm_severity"]).lower()

    if metrics["avg_cpl_usd"] > float(MAX_ALLOWABLE_CPL_USD):
        reasons.append("max_cpl_exceeded")
    if metrics["buyer_response_sla_ms"] > BUYER_RESPONSE_SLA_MS:
        reasons.append("buyer_response_sla_breached")
    if metrics["funded_buyers"] < MIN_FUNDED_BUYERS:
        reasons.append("insufficient_funded_buyers")
    if metrics["wallet_runway_usd"] < float(MIN_WALLET_RUNWAY_USD):
        reasons.append("insufficient_wallet_runway")

    if "max_cpl_exceeded" in reasons and "buyer_response_sla_breached" in reasons:
        return DecisionState.STOP_LOSS, reasons
    if reasons:
        return DecisionState.PAUSE, reasons
    if severity in {"high", "severe", "extreme"} and metrics["zip_coverage_count"] >= 25:
        return DecisionState.SCALE, ["storm_severity_high", "zip_coverage_sufficient"]
    if severity in {"moderate", "high", "severe", "extreme"}:
        return DecisionState.LAUNCH, ["storm_signal_present"]
    return DecisionState.HOLD, ["insufficient_storm_signal"]


@hatchet.workflow(on_events=["lead.captured"])
class QualifyLead:
    @hatchet.step(timeout="120s", retries=2)
    async def step(self, context: Context) -> dict:
        return await qualify_lead(context)


@hatchet.workflow(on_crons=["0 9 * * 1"])
class HermesSelfEvolution:
    @hatchet.step(timeout="600s", retries=1)
    async def step(self, context: Context) -> dict:
        return await hermes_self_evolution(context)


@hatchet.workflow(name="campaign-orchestrator", on_events=["storm_event.updated"], on_crons=["*/30 * * * *"])
class CampaignOrchestrator:
    @hatchet.step(timeout="180s", retries=1)
    async def step(self, context: Context) -> dict:
        return await run_campaign_orchestrator(context)


def main() -> None:
    worker = hatchet.worker("agent-runtime", max_runs=4)
    worker.register_workflow(QualifyLead())
    worker.register_workflow(HermesSelfEvolution())
    worker.register_workflow(CampaignOrchestrator())
    asyncio.run(worker.async_start())


if __name__ == "__main__":
    main()
