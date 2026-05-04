from stormlead_core.models import LeadClass, LeadQualifierInput, LeadQualifierOutput

from agent_runtime.roles.common import apply_human_override


def run_lead_qualifier(payload: LeadQualifierInput) -> LeadQualifierOutput:
    if not payload.consent_present:
        cls = LeadClass.D
        decision = "reject"
        conf = 0.95
        reason = "missing_consent"
    elif payload.photo_count > 0 and payload.damage_description:
        cls = LeadClass.A
        decision = "qualify"
        conf = 0.85
        reason = "damage_evidence_strong"
    else:
        cls = LeadClass.C
        decision = "review"
        conf = 0.55
        reason = "incomplete_damage_signal"
    out = LeadQualifierOutput(
        decision=decision,
        confidence=conf,
        reason_codes=[reason],
        idempotency_key=payload.workflow.idempotency_key,
        lead_class=cls,
        reason=reason,
    )
    return apply_human_override(out, payload.workflow)
