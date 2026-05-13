from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from agent_runtime.budget_pacing import (
    BudgetPacingAction,
    BudgetPacingPolicy,
    BudgetPacingStatus,
    CampaignPacingMetrics,
    evaluate_budget_pacing,
)


def _policy(
    *,
    max_cpl_cents: int = 10_000,
    min_roas: float = 1.0,
    min_sample_spend_cents: int = 5_000,
    min_sample_clicks: int = 25,
    no_lead_stop_loss_cents: int = 7_500,
    max_daily_budget_cents: int = 25_000,
    cooldown_hours: int = 24,
    paused_platforms: frozenset[str] = frozenset(),
) -> BudgetPacingPolicy:
    return BudgetPacingPolicy(
        max_cpl_cents=max_cpl_cents,
        min_roas=min_roas,
        min_sample_spend_cents=min_sample_spend_cents,
        min_sample_clicks=min_sample_clicks,
        no_lead_stop_loss_cents=no_lead_stop_loss_cents,
        max_daily_budget_cents=max_daily_budget_cents,
        cooldown_hours=cooldown_hours,
        paused_platforms=paused_platforms,
    )


def _metrics(
    *,
    campaign_id: UUID | None = None,
    platform: str = "google_ads",
    external_campaign_id: str = "campaign-123",
    current_daily_budget_cents: int = 10_000,
    spend_cents: int = 4_000,
    clicks: int = 10,
    qualified_leads: int = 1,
    gross_revenue_cents: int = 12_000,
    proposed_daily_budget_cents: int | None = None,
    last_budget_action_at: datetime | None = None,
    now: datetime = datetime(2026, 5, 13, tzinfo=UTC),
) -> CampaignPacingMetrics:
    return CampaignPacingMetrics(
        campaign_id=campaign_id or uuid4(),
        platform=platform,
        external_campaign_id=external_campaign_id,
        current_daily_budget_cents=current_daily_budget_cents,
        spend_cents=spend_cents,
        clicks=clicks,
        qualified_leads=qualified_leads,
        gross_revenue_cents=gross_revenue_cents,
        proposed_daily_budget_cents=proposed_daily_budget_cents,
        last_budget_action_at=last_budget_action_at,
        now=now,
    )


def test_lossy_campaign_recommends_local_auto_pause_audit_action() -> None:
    decision = evaluate_budget_pacing(
        _metrics(spend_cents=20_000, clicks=75, qualified_leads=1, gross_revenue_cents=5_000),
        _policy(),
    )

    assert decision.action == BudgetPacingAction.AUTO_PAUSE
    assert decision.status == BudgetPacingStatus.PLANNED
    assert decision.reason == "loss_threshold_exceeded"
    assert decision.approval_required is False

    audit_values = decision.audit_log_values()
    assert audit_values["action"] == "auto_pause"
    assert audit_values["status"] == "planned"
    assert audit_values["reason"] == "loss_threshold_exceeded"
    idempotency_key = cast(str, audit_values["idempotency_key"])
    assert idempotency_key.startswith("budget-pacing:auto_pause:")
    assert len(idempotency_key) <= 128
    audit_metrics = cast(dict[str, Any], audit_values["metrics_json"])
    audit_decision = cast(dict[str, Any], audit_values["decision_json"])
    assert audit_metrics["cpl_cents"] == 20_000
    assert audit_decision["would_contact_ads_provider"] is False
    assert audit_decision["would_mutate_ads_provider"] is False
    assert audit_decision["would_spend_money"] is False


def test_idempotency_key_is_bounded_and_changes_with_evaluation_snapshot() -> None:
    campaign_id = uuid4()
    first_decision = evaluate_budget_pacing(
        _metrics(
            campaign_id=campaign_id,
            external_campaign_id="x" * 128,
            spend_cents=20_000,
            clicks=75,
            qualified_leads=1,
            gross_revenue_cents=5_000,
        ),
        _policy(),
    )
    later_decision = evaluate_budget_pacing(
        _metrics(
            campaign_id=campaign_id,
            external_campaign_id="x" * 128,
            spend_cents=21_000,
            clicks=75,
            qualified_leads=1,
            gross_revenue_cents=5_000,
        ),
        _policy(),
    )

    assert len(first_decision.idempotency_key) <= 128
    assert first_decision.idempotency_key != later_decision.idempotency_key


def test_budget_increase_requires_admin_approval_and_does_not_spend() -> None:
    decision = evaluate_budget_pacing(
        _metrics(proposed_daily_budget_cents=12_500),
        _policy(),
    )

    assert decision.action == BudgetPacingAction.PROPOSE_INCREASE
    assert decision.status == BudgetPacingStatus.APPROVAL_REQUIRED
    assert decision.reason == "budget_increase_requires_admin_approval"
    assert decision.approval_required is True
    assert decision.decision["approval_required_before_live_ads_action"] is True
    assert decision.decision["would_contact_ads_provider"] is False
    assert decision.decision["would_mutate_ads_provider"] is False
    assert decision.decision["would_spend_money"] is False


def test_budget_increase_above_cap_is_blocked_without_provider_mutation() -> None:
    decision = evaluate_budget_pacing(
        _metrics(proposed_daily_budget_cents=30_000),
        _policy(max_daily_budget_cents=25_000),
    )

    assert decision.action == BudgetPacingAction.BLOCK_INCREASE
    assert decision.status == BudgetPacingStatus.BLOCKED
    assert decision.reason == "proposed_daily_budget_exceeds_cap"
    assert decision.approval_required is False
    audit_values = decision.audit_log_values()
    audit_decision = cast(dict[str, Any], audit_values["decision_json"])
    assert audit_decision["would_mutate_ads_provider"] is False


def test_minimum_sample_and_cooldown_prevent_pause_flapping() -> None:
    too_early = evaluate_budget_pacing(
        _metrics(spend_cents=4_000, clicks=10, qualified_leads=0, gross_revenue_cents=0),
        _policy(),
    )
    assert too_early.action == BudgetPacingAction.HOLD
    assert too_early.reason == "within_budget_pacing_policy"

    now = datetime(2026, 5, 13, tzinfo=UTC)
    cooldown = evaluate_budget_pacing(
        _metrics(
            spend_cents=20_000,
            clicks=75,
            qualified_leads=0,
            gross_revenue_cents=0,
            now=now,
            last_budget_action_at=now - timedelta(hours=2),
        ),
        _policy(),
    )
    assert cooldown.action == BudgetPacingAction.HOLD
    assert cooldown.status == BudgetPacingStatus.SKIPPED
    assert cooldown.reason == "cooldown_active"


def test_cooldown_holds_budget_increase_proposals() -> None:
    now = datetime(2026, 5, 13, tzinfo=UTC)
    decision = evaluate_budget_pacing(
        _metrics(
            proposed_daily_budget_cents=12_500,
            now=now,
            last_budget_action_at=now - timedelta(hours=2),
        ),
        _policy(),
    )

    assert decision.action == BudgetPacingAction.HOLD
    assert decision.status == BudgetPacingStatus.SKIPPED
    assert decision.reason == "cooldown_active"


def test_no_lead_stop_loss_can_pause_before_general_sample_threshold() -> None:
    decision = evaluate_budget_pacing(
        _metrics(spend_cents=4_000, clicks=10, qualified_leads=0, gross_revenue_cents=0),
        _policy(min_sample_spend_cents=5_000, min_sample_clicks=25, no_lead_stop_loss_cents=3_000),
    )

    assert decision.action == BudgetPacingAction.AUTO_PAUSE
    assert decision.status == BudgetPacingStatus.PLANNED
    assert decision.reason == "no_lead_stop_loss_exceeded"


def test_platform_kill_switch_holds_budget_actions() -> None:
    decision = evaluate_budget_pacing(
        _metrics(platform="meta", proposed_daily_budget_cents=12_500),
        _policy(paused_platforms=frozenset({"meta"})),
    )

    assert decision.action == BudgetPacingAction.HOLD
    assert decision.status == BudgetPacingStatus.SKIPPED
    assert decision.reason == "platform_kill_switch_paused"
    assert decision.decision["would_contact_ads_provider"] is False
