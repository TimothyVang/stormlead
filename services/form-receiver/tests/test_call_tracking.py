from __future__ import annotations

from form_receiver.call_tracking import CallTrackingEvent


def test_call_tracking_event_parses_valid_payload() -> None:
    event = CallTrackingEvent.model_validate(
        {
            "call_id": "test-001",
            "phone_e164": "+13215550001",
            "duration_seconds": 60,
            "outcome": "answered",
            "tracked_at": "2026-05-04T12:00:00Z",
        }
    )
    assert event.call_id == "test-001"
    assert event.outcome.value == "answered"
