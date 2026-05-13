from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from voice_bridge.main import app


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_follow_up_preview_stays_local_and_parks_provider_action() -> None:
    lead_id = uuid4()

    response = TestClient(app).post(
        "/v1/follow-up/preview",
        json={
            "lead_id": str(lead_id),
            "phone_e164": "+13215550123",
            "lead_status": "qualified",
            "consent_text": "I agree to be contacted about my tree damage request.",
            "attempt_count": 1,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "local_preview"
    assert body["lead_id"] == str(lead_id)
    assert body["eligible_for_follow_up"] is True
    assert body["blocked_reasons"] == []
    assert body["live_call_allowed"] is False
    assert body["would_contact_phone_provider"] is False
    assert body["provider_action"] == "parked_until_explicit_approval"
    assert body["remaining_attempts"] == 2
    assert body["voicemail_policy"]["pii_heavy_content_allowed"] is False


def test_follow_up_preview_blocks_ineligible_or_over_attempted_lead() -> None:
    response = TestClient(app).post(
        "/v1/follow-up/preview",
        json={
            "lead_id": str(uuid4()),
            "phone_e164": "+13215550123",
            "lead_status": "safety_review",
            "consent_text": "I agree to be contacted about my tree damage request.",
            "attempt_count": 3,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["eligible_for_follow_up"] is False
    assert body["blocked_reasons"] == [
        "lead_status_not_follow_up_eligible",
        "max_attempts_reached",
    ]
    assert body["would_contact_phone_provider"] is False


def test_follow_up_preview_rejects_non_e164_phone() -> None:
    response = TestClient(app).post(
        "/v1/follow-up/preview",
        json={
            "lead_id": str(uuid4()),
            "phone_e164": "3215550123",
            "lead_status": "qualified",
            "consent_text": "I agree to be contacted about my tree damage request.",
        },
    )

    assert response.status_code == 422
