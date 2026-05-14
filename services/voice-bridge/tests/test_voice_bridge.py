from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from voice_bridge.main import app


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_advertises_local_preview_only() -> None:
    response = TestClient(app).get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "local_preview_only": True}


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


def test_inbound_call_preview_models_intake_without_provider_contact() -> None:
    response = TestClient(app).post(
        "/v1/inbound/preview",
        json={
            "call_id": "call-local-123",
            "from_phone_e164": "+13215550123",
            "to_phone_e164": "+18885550100",
            "transcript_text": "Caller reports a fallen tree across the driveway.",
            "photo_link_url": "https://example.invalid/local-photo-upload-token",
            "consent_text": "Caller agrees to be contacted about the tree damage request.",
            "requested_service": "tree_removal",
            "damage_description": "Fallen tree across driveway.",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "local_preview"
    assert body["intake_status"] == "ready_for_operator_review"
    assert body["blocked_reasons"] == []
    assert body["modeled_fields"]["transcript_text"] is True
    assert body["modeled_fields"]["photo_link_url"] is True
    assert body["modeled_fields"]["consent_text"] is True
    assert body["live_call_allowed"] is False
    assert body["would_contact_phone_provider"] is False
    assert body["photo_link_policy"]["would_fetch_remote_url"] is False


def test_inbound_call_preview_holds_unsafe_calls() -> None:
    response = TestClient(app).post(
        "/v1/inbound/preview",
        json={
            "call_id": "call-local-unsafe",
            "from_phone_e164": "+13215550123",
            "to_phone_e164": "+18885550100",
            "transcript_text": "Caller reports a tree on a power line.",
            "consent_text": "Caller agrees to be contacted about the tree damage request.",
            "power_line_involved": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intake_status"] == "held_for_safety_review"
    assert body["unsafe_call_held"] is True
    assert "unsafe_call_safety_escalation" in body["blocked_reasons"]
    assert body["would_contact_phone_provider"] is False


def test_inbound_call_preview_blocks_missing_transcript_or_consent() -> None:
    response = TestClient(app).post(
        "/v1/inbound/preview",
        json={
            "call_id": "call-local-missing-fields",
            "from_phone_e164": "+13215550123",
            "to_phone_e164": "+18885550100",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intake_status"] == "blocked_missing_required_fields"
    assert body["blocked_reasons"] == ["missing_transcript_text", "missing_consent_text"]
    assert body["modeled_fields"]["transcript_text"] is False
    assert body["modeled_fields"]["consent_text"] is False
    assert body["would_contact_phone_provider"] is False


def test_inbound_call_preview_rejects_non_http_photo_link() -> None:
    response = TestClient(app).post(
        "/v1/inbound/preview",
        json={
            "call_id": "call-local-bad-photo",
            "from_phone_e164": "+13215550123",
            "to_phone_e164": "+18885550100",
            "transcript_text": "Caller has photos.",
            "photo_link_url": "ftp://example.invalid/photo.jpg",
            "consent_text": "Caller agrees to be contacted about the tree damage request.",
        },
    )

    assert response.status_code == 422


def test_inbound_call_preview_rejects_non_e164_phone_numbers() -> None:
    response = TestClient(app).post(
        "/v1/inbound/preview",
        json={
            "call_id": "call-local-bad-phone",
            "from_phone_e164": "3215550123",
            "to_phone_e164": "8885550100",
            "transcript_text": "Caller reports tree damage.",
            "consent_text": "Caller agrees to be contacted about the tree damage request.",
        },
    )

    assert response.status_code == 422
