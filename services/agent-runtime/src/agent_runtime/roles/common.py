from __future__ import annotations

from stormlead_core.models import AgentDecisionOutput, HumanOverrideMode, RetrySafeExecution, WorkflowContext


DISPUTE_SENSITIVE_DECISIONS = {"refund", "partial_refund"}


def retry_safe(workflow: WorkflowContext, dedupe_scope: str, already_processed: bool) -> RetrySafeExecution:
    return RetrySafeExecution(
        idempotency_key=workflow.idempotency_key,
        dedupe_scope=dedupe_scope,
        should_execute_side_effects=workflow.allow_charges_or_posts and not already_processed,
    )


def apply_human_override(output: AgentDecisionOutput, workflow: WorkflowContext) -> AgentDecisionOutput:
    low_conf = output.confidence < workflow.min_confidence_for_autonomy
    dispute_sensitive = output.decision in DISPUTE_SENSITIVE_DECISIONS
    if workflow.human_override_mode == HumanOverrideMode.STRICT:
        output.requires_human_review = True
    elif workflow.human_override_mode == HumanOverrideMode.LOW_CONFIDENCE_ONLY and (low_conf or dispute_sensitive):
        output.requires_human_review = True
    return output
