from stormlead_core.models import NurtureControllerInput, NurtureControllerOutput

from agent_runtime.roles.common import apply_human_override


def run_nurture_controller(payload: NurtureControllerInput) -> NurtureControllerOutput:
    if payload.prior_attempt_count >= 3:
        decision = "archive"
        confidence = 0.82
        reason = "max_attempts_reached"
    else:
        decision = "retry_contact"
        confidence = 0.72
        reason = "continue_nurture"
    out = NurtureControllerOutput(
        decision=decision,
        confidence=confidence,
        reason_codes=[reason],
        idempotency_key=payload.workflow.idempotency_key,
    )
    return apply_human_override(out, payload.workflow)
