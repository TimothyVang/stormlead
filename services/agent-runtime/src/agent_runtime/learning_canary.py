"""Local learning-proposal replay and canary guardrails.

This module only evaluates local metrics. It does not route live traffic,
promote proposals, or contact external providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LearningCanaryStatus = Literal[
    "pending_replay",
    "canary_active",
    "rollback_triggered",
    "pending_approval",
]


@dataclass(frozen=True)
class LearningCanaryPolicy:
    canary_percent: int = 5
    rollback_threshold_pct: float = 5.0
    minimum_replay_sample: int = 30
    guardrail_metric: str = "conversion_rate"

    def __post_init__(self) -> None:
        if not 1 <= self.canary_percent <= 99:
            raise ValueError("canary_percent must be between 1 and 99")
        if self.rollback_threshold_pct < 0:
            raise ValueError("rollback_threshold_pct must be nonnegative")
        if self.minimum_replay_sample < 1:
            raise ValueError("minimum_replay_sample must be positive")
        if not self.guardrail_metric:
            raise ValueError("guardrail_metric is required")


@dataclass(frozen=True)
class LearningProposalMetrics:
    baseline_conversions: int
    baseline_total: int
    candidate_conversions: int
    candidate_total: int

    def __post_init__(self) -> None:
        values = (
            self.baseline_conversions,
            self.baseline_total,
            self.candidate_conversions,
            self.candidate_total,
        )
        if any(value < 0 for value in values):
            raise ValueError("metrics must be nonnegative")
        if self.baseline_conversions > self.baseline_total:
            raise ValueError("baseline_conversions cannot exceed baseline_total")
        if self.candidate_conversions > self.candidate_total:
            raise ValueError("candidate_conversions cannot exceed candidate_total")


@dataclass(frozen=True)
class LearningCanaryDecision:
    status: LearningCanaryStatus
    canary_percent: int
    approval_required: bool
    rollback_required: bool
    reason: str
    guardrail_metric: str
    baseline_rate: float
    candidate_rate: float
    relative_drop_pct: float

    def replay_result_json(self) -> dict[str, float | int | str | bool]:
        return {
            "status": self.status,
            "canary_percent": self.canary_percent,
            "approval_required": self.approval_required,
            "rollback_required": self.rollback_required,
            "reason": self.reason,
            "guardrail_metric": self.guardrail_metric,
            "baseline_rate": self.baseline_rate,
            "candidate_rate": self.candidate_rate,
            "relative_drop_pct": self.relative_drop_pct,
        }


def _conversion_rate(conversions: int, total: int) -> float:
    if total == 0:
        return 0.0
    return conversions / total


def _relative_drop_pct(baseline_rate: float, candidate_rate: float) -> float:
    if baseline_rate <= 0:
        return 0.0
    return max(0.0, ((baseline_rate - candidate_rate) / baseline_rate) * 100.0)


def evaluate_replay_for_canary(
    metrics: LearningProposalMetrics,
    policy: LearningCanaryPolicy | None = None,
) -> LearningCanaryDecision:
    policy = policy or LearningCanaryPolicy()
    baseline_rate = _conversion_rate(metrics.baseline_conversions, metrics.baseline_total)
    candidate_rate = _conversion_rate(metrics.candidate_conversions, metrics.candidate_total)
    relative_drop_pct = _relative_drop_pct(baseline_rate, candidate_rate)

    if (
        metrics.baseline_total < policy.minimum_replay_sample
        or metrics.candidate_total < policy.minimum_replay_sample
    ):
        return LearningCanaryDecision(
            status="pending_replay",
            canary_percent=0,
            approval_required=False,
            rollback_required=False,
            reason="Replay sample is below the configured minimum; do not canary yet.",
            guardrail_metric=policy.guardrail_metric,
            baseline_rate=baseline_rate,
            candidate_rate=candidate_rate,
            relative_drop_pct=relative_drop_pct,
        )

    if relative_drop_pct > policy.rollback_threshold_pct:
        return LearningCanaryDecision(
            status="rollback_triggered",
            canary_percent=0,
            approval_required=False,
            rollback_required=True,
            reason="Candidate conversion rate regressed beyond the rollback threshold.",
            guardrail_metric=policy.guardrail_metric,
            baseline_rate=baseline_rate,
            candidate_rate=candidate_rate,
            relative_drop_pct=relative_drop_pct,
        )

    return LearningCanaryDecision(
        status="canary_active",
        canary_percent=policy.canary_percent,
        approval_required=False,
        rollback_required=False,
        reason="Replay guardrail passed; stage the proposal to the configured canary percent.",
        guardrail_metric=policy.guardrail_metric,
        baseline_rate=baseline_rate,
        candidate_rate=candidate_rate,
        relative_drop_pct=relative_drop_pct,
    )


def evaluate_manual_promotion_gate(
    metrics: LearningProposalMetrics,
    policy: LearningCanaryPolicy | None = None,
) -> LearningCanaryDecision:
    decision = evaluate_replay_for_canary(metrics, policy)
    if decision.status != "canary_active":
        return decision

    return LearningCanaryDecision(
        status="pending_approval",
        canary_percent=decision.canary_percent,
        approval_required=True,
        rollback_required=False,
        reason="Guardrails passed, but 100% promotion requires explicit admin approval.",
        guardrail_metric=decision.guardrail_metric,
        baseline_rate=decision.baseline_rate,
        candidate_rate=decision.candidate_rate,
        relative_drop_pct=decision.relative_drop_pct,
    )
