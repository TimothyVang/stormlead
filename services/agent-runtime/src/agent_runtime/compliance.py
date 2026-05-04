from __future__ import annotations

CONSENT_REQUIRED_RECORDING_STATES = {"CA", "FL", "IL", "MD", "MA", "MT", "NH", "NV", "PA", "WA"}


def should_record_call(*, state: str, has_recording_consent: bool) -> bool:
    state_u = state.upper()
    if state_u in CONSENT_REQUIRED_RECORDING_STATES:
        return has_recording_consent
    return True
