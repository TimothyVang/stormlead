from stormlead_core.models import BuyerMatcherInput, BuyerMatcherOutput, RankedBuyer

from agent_runtime.roles.common import apply_human_override


def run_buyer_matcher(payload: BuyerMatcherInput) -> BuyerMatcherOutput:
    ranked = [RankedBuyer(buyer_id=bid, rank=i + 1, score=max(0.1, 1 - i * 0.1)) for i, bid in enumerate(payload.candidate_buyer_ids)]
    out = BuyerMatcherOutput(
        decision="match" if ranked else "no_match",
        confidence=0.78 if ranked else 0.7,
        reason_codes=["capacity_fit" if ranked else "no_eligible_buyers"],
        idempotency_key=payload.workflow.idempotency_key,
        eligible_buyers=ranked,
    )
    return apply_human_override(out, payload.workflow)
