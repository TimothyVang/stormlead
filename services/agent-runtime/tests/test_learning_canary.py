from __future__ import annotations

import pytest
from agent_runtime.learning_canary import (
    LearningCanaryPolicy,
    LearningProposalMetrics,
    evaluate_manual_promotion_gate,
    evaluate_replay_for_canary,
)


def test_replay_pass_stages_five_percent_canary() -> None:
    decision = evaluate_replay_for_canary(
        LearningProposalMetrics(
            baseline_conversions=60,
            baseline_total=100,
            candidate_conversions=59,
            candidate_total=100,
        ),
        LearningCanaryPolicy(canary_percent=5, rollback_threshold_pct=10.0),
    )

    assert decision.status == "canary_active"
    assert decision.canary_percent == 5
    assert decision.approval_required is False
    assert decision.rollback_required is False
    assert decision.replay_result_json()["status"] == "canary_active"


def test_replay_regression_triggers_automatic_rollback() -> None:
    decision = evaluate_replay_for_canary(
        LearningProposalMetrics(
            baseline_conversions=60,
            baseline_total=100,
            candidate_conversions=45,
            candidate_total=100,
        ),
        LearningCanaryPolicy(canary_percent=5, rollback_threshold_pct=10.0),
    )

    assert decision.status == "rollback_triggered"
    assert decision.canary_percent == 0
    assert decision.approval_required is False
    assert decision.rollback_required is True
    assert decision.relative_drop_pct > 10.0


def test_manual_promotion_gate_requires_admin_approval_for_full_rollout() -> None:
    decision = evaluate_manual_promotion_gate(
        LearningProposalMetrics(
            baseline_conversions=60,
            baseline_total=100,
            candidate_conversions=60,
            candidate_total=100,
        )
    )

    assert decision.status == "pending_approval"
    assert decision.canary_percent == 5
    assert decision.approval_required is True
    assert "100% promotion" in decision.reason


def test_small_replay_sample_does_not_start_canary() -> None:
    decision = evaluate_replay_for_canary(
        LearningProposalMetrics(
            baseline_conversions=1,
            baseline_total=2,
            candidate_conversions=2,
            candidate_total=2,
        )
    )

    assert decision.status == "pending_replay"
    assert decision.canary_percent == 0
    assert decision.approval_required is False


def test_invalid_metrics_are_rejected() -> None:
    with pytest.raises(ValueError, match="candidate_conversions"):
        LearningProposalMetrics(
            baseline_conversions=1,
            baseline_total=1,
            candidate_conversions=2,
            candidate_total=1,
        )
