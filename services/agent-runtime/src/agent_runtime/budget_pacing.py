from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

BudgetJsonValue = int | float | bool | str | None


class BudgetPacingAction(StrEnum):
    AUTO_PAUSE = "auto_pause"
    PROPOSE_INCREASE = "propose_increase"
    BLOCK_INCREASE = "block_increase"
    HOLD = "hold"


class BudgetPacingStatus(StrEnum):
    PLANNED = "planned"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class BudgetPacingPolicy:
    max_cpl_cents: int
    min_roas: float
    min_sample_spend_cents: int
    min_sample_clicks: int
    no_lead_stop_loss_cents: int
    max_daily_budget_cents: int
    cooldown_hours: int = 24
    paused_platforms: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CampaignPacingMetrics:
    campaign_id: UUID
    platform: str
    external_campaign_id: str
    current_daily_budget_cents: int
    spend_cents: int
    clicks: int
    qualified_leads: int
    gross_revenue_cents: int
    proposed_daily_budget_cents: int | None = None
    last_budget_action_at: datetime | None = None
    now: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class BudgetPacingDecision:
    campaign_id: UUID
    platform: str
    external_campaign_id: str
    action: BudgetPacingAction
    status: BudgetPacingStatus
    reason: str
    approval_required: bool
    idempotency_key: str
    metrics: dict[str, BudgetJsonValue]
    decision: dict[str, BudgetJsonValue]

    def audit_log_values(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "platform": self.platform,
            "external_campaign_id": self.external_campaign_id,
            "action": self.action.value,
            "status": self.status.value,
            "approval_required": self.approval_required,
            "reason": self.reason,
            "idempotency_key": self.idempotency_key,
            "metrics_json": self.metrics,
            "decision_json": self.decision,
        }


def evaluate_budget_pacing(
    metrics: CampaignPacingMetrics,
    policy: BudgetPacingPolicy,
) -> BudgetPacingDecision:
    cpl_cents = _cost_per_lead_cents(metrics.spend_cents, metrics.qualified_leads)
    roas = _roas(metrics.gross_revenue_cents, metrics.spend_cents)
    sample_ready = _sample_ready(metrics, policy)
    cooldown_active = _cooldown_active(metrics, policy)
    metrics_json: dict[str, BudgetJsonValue] = {
        "current_daily_budget_cents": metrics.current_daily_budget_cents,
        "spend_cents": metrics.spend_cents,
        "clicks": metrics.clicks,
        "qualified_leads": metrics.qualified_leads,
        "gross_revenue_cents": metrics.gross_revenue_cents,
        "proposed_daily_budget_cents": metrics.proposed_daily_budget_cents,
        "cpl_cents": cpl_cents,
        "roas": roas,
        "sample_ready": sample_ready,
        "cooldown_active": cooldown_active,
    }

    if metrics.platform in policy.paused_platforms:
        return _decision(
            metrics,
            BudgetPacingAction.HOLD,
            BudgetPacingStatus.SKIPPED,
            "platform_kill_switch_paused",
            False,
            metrics_json,
            policy,
        )

    if metrics.proposed_daily_budget_cents is not None:
        if metrics.proposed_daily_budget_cents > policy.max_daily_budget_cents:
            return _decision(
                metrics,
                BudgetPacingAction.BLOCK_INCREASE,
                BudgetPacingStatus.BLOCKED,
                "proposed_daily_budget_exceeds_cap",
                False,
                metrics_json,
                policy,
            )

    if cooldown_active:
        return _decision(
            metrics,
            BudgetPacingAction.HOLD,
            BudgetPacingStatus.SKIPPED,
            "cooldown_active",
            False,
            metrics_json,
            policy,
        )

    if _no_lead_stop_loss_exceeded(metrics, policy):
        return _decision(
            metrics,
            BudgetPacingAction.AUTO_PAUSE,
            BudgetPacingStatus.PLANNED,
            "no_lead_stop_loss_exceeded",
            False,
            metrics_json,
            policy,
        )

    if sample_ready and _loss_threshold_exceeded(metrics, policy, cpl_cents, roas):
        return _decision(
            metrics,
            BudgetPacingAction.AUTO_PAUSE,
            BudgetPacingStatus.PLANNED,
            "loss_threshold_exceeded",
            False,
            metrics_json,
            policy,
        )

    if (
        metrics.proposed_daily_budget_cents is not None
        and metrics.proposed_daily_budget_cents > metrics.current_daily_budget_cents
    ):
        return _decision(
            metrics,
            BudgetPacingAction.PROPOSE_INCREASE,
            BudgetPacingStatus.APPROVAL_REQUIRED,
            "budget_increase_requires_admin_approval",
            True,
            metrics_json,
            policy,
        )

    return _decision(
        metrics,
        BudgetPacingAction.HOLD,
        BudgetPacingStatus.SKIPPED,
        "within_budget_pacing_policy",
        False,
        metrics_json,
        policy,
    )


def _decision(
    metrics: CampaignPacingMetrics,
    action: BudgetPacingAction,
    status: BudgetPacingStatus,
    reason: str,
    approval_required: bool,
    metrics_json: dict[str, BudgetJsonValue],
    policy: BudgetPacingPolicy,
) -> BudgetPacingDecision:
    fingerprint = _evaluation_fingerprint(metrics, action)
    decision_json: dict[str, BudgetJsonValue] = {
        "max_cpl_cents": policy.max_cpl_cents,
        "min_roas": policy.min_roas,
        "min_sample_spend_cents": policy.min_sample_spend_cents,
        "min_sample_clicks": policy.min_sample_clicks,
        "no_lead_stop_loss_cents": policy.no_lead_stop_loss_cents,
        "max_daily_budget_cents": policy.max_daily_budget_cents,
        "cooldown_hours": policy.cooldown_hours,
        "would_contact_ads_provider": False,
        "would_mutate_ads_provider": False,
        "would_spend_money": False,
        "approval_required_before_live_ads_action": approval_required,
        "evaluation_date": metrics.now.date().isoformat(),
        "metrics_fingerprint": fingerprint,
    }
    return BudgetPacingDecision(
        campaign_id=metrics.campaign_id,
        platform=metrics.platform,
        external_campaign_id=metrics.external_campaign_id,
        action=action,
        status=status,
        reason=reason,
        approval_required=approval_required,
        idempotency_key=f"budget-pacing:{action.value}:{fingerprint[:32]}",
        metrics=metrics_json,
        decision=decision_json,
    )


def _cost_per_lead_cents(spend_cents: int, qualified_leads: int) -> int | None:
    if qualified_leads <= 0:
        return None
    return spend_cents // qualified_leads


def _roas(gross_revenue_cents: int, spend_cents: int) -> float | None:
    if spend_cents <= 0:
        return None
    return round(gross_revenue_cents / spend_cents, 4)


def _sample_ready(metrics: CampaignPacingMetrics, policy: BudgetPacingPolicy) -> bool:
    return (
        metrics.spend_cents >= policy.min_sample_spend_cents
        or metrics.clicks >= policy.min_sample_clicks
    )


def _cooldown_active(metrics: CampaignPacingMetrics, policy: BudgetPacingPolicy) -> bool:
    if metrics.last_budget_action_at is None:
        return False
    last_action_at = metrics.last_budget_action_at
    if last_action_at.tzinfo is None:
        last_action_at = last_action_at.replace(tzinfo=UTC)
    return metrics.now - last_action_at < timedelta(hours=policy.cooldown_hours)


def _loss_threshold_exceeded(
    metrics: CampaignPacingMetrics,
    policy: BudgetPacingPolicy,
    cpl_cents: int | None,
    roas: float | None,
) -> bool:
    if cpl_cents is not None and cpl_cents > policy.max_cpl_cents:
        return True
    return (
        roas is not None
        and roas < policy.min_roas
        and metrics.spend_cents > metrics.gross_revenue_cents
    )


def _no_lead_stop_loss_exceeded(
    metrics: CampaignPacingMetrics,
    policy: BudgetPacingPolicy,
) -> bool:
    return metrics.qualified_leads <= 0 and metrics.spend_cents >= policy.no_lead_stop_loss_cents


def _evaluation_fingerprint(
    metrics: CampaignPacingMetrics,
    action: BudgetPacingAction,
) -> str:
    parts = [
        metrics.campaign_id.hex,
        metrics.platform,
        metrics.external_campaign_id,
        action.value,
        metrics.now.date().isoformat(),
        str(metrics.current_daily_budget_cents),
        str(metrics.proposed_daily_budget_cents),
        str(metrics.spend_cents),
        str(metrics.clicks),
        str(metrics.qualified_leads),
        str(metrics.gross_revenue_cents),
    ]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()
