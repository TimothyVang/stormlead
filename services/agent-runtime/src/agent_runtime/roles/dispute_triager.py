from stormlead_core.models import DisputeTriagerInput, DisputeTriagerOutput

from agent_runtime.roles.common import apply_human_override


def run_dispute_triager(payload: DisputeTriagerInput) -> DisputeTriagerOutput:
    if "wrong number" in payload.dispute_reason.lower():
        decision = "refund"
        refund = payload.requested_refund_cents
        confidence = 0.9
        reason_codes = ["invalid_lead_contact"]
    else:
        decision = "review"
        refund = None
        confidence = 0.5
        reason_codes = ["manual_dispute_review"]
    out = DisputeTriagerOutput(
        decision=decision,
        confidence=confidence,
        reason_codes=reason_codes,
        idempotency_key=payload.workflow.idempotency_key,
        recommended_refund_cents=refund,
    )
    return apply_human_override(out, payload.workflow)
