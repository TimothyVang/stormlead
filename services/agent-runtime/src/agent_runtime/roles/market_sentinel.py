from stormlead_core.models import MarketSentinelInput, MarketSentinelOutput

from agent_runtime.roles.common import apply_human_override


def run_market_sentinel(payload: MarketSentinelInput) -> MarketSentinelOutput:
    readiness = min(1.0, (payload.open_lead_count / 100) + (payload.active_buyer_count / 50))
    decision = "ready" if readiness >= 0.7 else "monitor"
    out = MarketSentinelOutput(
        decision=decision,
        confidence=0.8 if decision == "ready" else 0.65,
        reason_codes=["lead_volume", "buyer_capacity"],
        idempotency_key=payload.workflow.idempotency_key,
        readiness_score=readiness,
    )
    return apply_human_override(out, payload.workflow)
