from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from form_receiver.api import app
from form_receiver.storage import CaptureWebhookStatus, DuplicateLeadError

SECRET = "whsec_" + base64.b64encode(b"unit-test-secret-32-bytes-padded!").decode()


def _sign(webhook_id: str, ts: str, body: bytes, secret: str = SECRET) -> str:
    raw_secret = base64.b64decode(secret.removeprefix("whsec_") + "==")
    signed = f"{webhook_id}.{ts}.".encode() + body
    sig = base64.b64encode(hmac.new(raw_secret, signed, hashlib.sha256).digest()).decode()
    return f"v1,{sig}"


def _formbricks_body(*, webhook_id: str) -> bytes:
    return json.dumps(
        {
            "event": "responseFinished",
            "webhookId": webhook_id,
            "data": {
                "id": "resp_duplicate_test",
                "surveyId": "survey_test",
                "data": {
                    "name": "Test User",
                    "phone": "+15125550123",
                    "email": "test@example.com",
                    "address_line1": "100 Main St",
                    "city": "Austin",
                    "state": "TX",
                    "zip": "78701",
                    "consent_text": "I agree to be contacted.",
                    "consent_version": "tree-damage-intake-v1",
                    "requested_service": "tree_removal",
                    "damage_type": "fallen_tree",
                    "urgency": "same_day",
                    "damage_description": "Fallen tree across the driveway.",
                    "power_line_involved": "false",
                    "injury_reported": "false",
                    "active_danger": "false",
                    "page_html_sha256": "b" * 64,
                    "gps_latitude": "30.4515",
                    "gps_longitude": "-91.1871",
                    "gps_accuracy_meters": "22",
                    "gps_captured_at": "2026-05-10T18:00:00Z",
                    "location_source": "browser_gps",
                    "location_confirmed_at": "2026-05-10T18:01:00Z",
                    "damage_photo_keys": '["wide.jpg", "close.jpg"]',
                },
                "ttc": {"name": 1200, "phone": 1800, "consent_text": 3000},
                "contactAttributes": {},
                "meta": {
                    "url": "https://example.test/landing",
                    "userAgent": "Mozilla/5.0 (test)",
                },
                "finished": True,
            },
        },
        separators=(",", ":"),
    ).encode()


def _location_photo_required_body(*, webhook_id: str) -> bytes:
    body = json.loads(_formbricks_body(webhook_id=webhook_id).decode())
    body["data"]["data"]["require_location_photo_verification"] = "true"
    for key in (
        "gps_latitude",
        "gps_longitude",
        "gps_accuracy_meters",
        "gps_captured_at",
        "location_source",
        "location_confirmed_at",
        "damage_photo_keys",
    ):
        body["data"]["data"].pop(key, None)
    return json.dumps(body, separators=(",", ":")).encode()


def test_formbricks_webhook_returns_409_for_duplicate_lead(monkeypatch) -> None:
    monkeypatch.setenv("FORMBRICKS_WEBHOOK_SECRET", SECRET)
    webhook_id = "evt_duplicate_test"
    body = _formbricks_body(webhook_id=webhook_id)
    ts = str(int(time.time()))
    duplicate_id = uuid4()

    with (
        patch(
            "form_receiver.api.capture_status_for_webhook",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "form_receiver.api.upsert_lead",
            new=AsyncMock(
                side_effect=DuplicateLeadError(
                    duplicate_id,
                    reason="duplicate_window_match",
                    window_hours=72,
                )
            ),
        ) as upsert,
        patch("form_receiver.api.record_audit", new=AsyncMock()) as record_audit,
    ):
        response = TestClient(app).post(
            "/webhooks/formbricks",
            content=body,
            headers={
                "content-type": "application/json",
                "webhook-id": webhook_id,
                "webhook-timestamp": ts,
                "webhook-signature": _sign(webhook_id, ts, body),
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "status": "duplicate",
        "reason": "duplicate_window_match",
        "window_hours": 72,
    }
    upsert.assert_awaited_once()
    record_audit.assert_not_awaited()


def test_formbricks_webhook_rejects_missing_required_location_photo_verification(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FORMBRICKS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("FORM_RECEIVER_REQUIRE_LOCATION_PHOTO_VERIFICATION", "true")
    webhook_id = "evt_missing_location_photo_test"
    body = _location_photo_required_body(webhook_id=webhook_id)
    ts = str(int(time.time()))

    with (
        patch("form_receiver.api.capture_status_for_webhook", new=AsyncMock()) as capture_lookup,
        patch("form_receiver.api.upsert_lead", new=AsyncMock()) as upsert,
    ):
        response = TestClient(app).post(
            "/webhooks/formbricks",
            content=body,
            headers={
                "content-type": "application/json",
                "webhook-id": webhook_id,
                "webhook-timestamp": ts,
                "webhook-signature": _sign(webhook_id, ts, body),
            },
        )

    assert response.status_code == 400
    assert "missing required GPS location" in response.json()["detail"]
    capture_lookup.assert_not_awaited()
    upsert.assert_not_awaited()


def test_formbricks_webhook_accepts_audited_retry(monkeypatch) -> None:
    monkeypatch.setenv("FORMBRICKS_WEBHOOK_SECRET", SECRET)
    webhook_id = "evt_retry_test"
    body = _formbricks_body(webhook_id=webhook_id)
    ts = str(int(time.time()))
    existing_id = uuid4()

    with (
        patch(
            "form_receiver.api.capture_status_for_webhook",
            new=AsyncMock(
                return_value=CaptureWebhookStatus(
                    lead_id=existing_id,
                    event_status="sent",
                    audit_recorded=True,
                )
            ),
        ) as capture_lookup,
        patch("form_receiver.api._hatchet", object()),
        patch("form_receiver.api.emit_lead_captured", new=AsyncMock()) as emit,
        patch("form_receiver.api.upsert_lead", new=AsyncMock()) as upsert,
        patch("form_receiver.api.record_audit", new=AsyncMock()) as record_audit,
    ):
        response = TestClient(app).post(
            "/webhooks/formbricks",
            content=body,
            headers={
                "content-type": "application/json",
                "webhook-id": webhook_id,
                "webhook-timestamp": ts,
                "webhook-signature": _sign(webhook_id, ts, body),
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted-duplicate"}
    capture_lookup.assert_awaited_once_with(webhook_id)
    emit.assert_not_awaited()
    upsert.assert_not_awaited()
    record_audit.assert_not_awaited()


def test_formbricks_webhook_retries_event_emit_for_audited_retry(monkeypatch) -> None:
    monkeypatch.setenv("FORMBRICKS_WEBHOOK_SECRET", SECRET)
    webhook_id = "evt_retry_emit_failure_test"
    body = _formbricks_body(webhook_id=webhook_id)
    ts = str(int(time.time()))
    existing_id = uuid4()

    with (
        patch(
            "form_receiver.api.capture_status_for_webhook",
            new=AsyncMock(
                return_value=CaptureWebhookStatus(
                    lead_id=existing_id,
                    event_status="pending",
                    audit_recorded=True,
                )
            ),
        ),
        patch("form_receiver.api.claim_capture_event_dispatch", new=AsyncMock(return_value=True)),
        patch("form_receiver.api._hatchet", object()),
        patch(
            "form_receiver.api.emit_lead_captured",
            new=AsyncMock(side_effect=RuntimeError("hatchet unavailable")),
        ) as emit,
        patch("form_receiver.api.mark_capture_event_failed", new=AsyncMock()) as mark_failed,
    ):
        response = TestClient(app).post(
            "/webhooks/formbricks",
            content=body,
            headers={
                "content-type": "application/json",
                "webhook-id": webhook_id,
                "webhook-timestamp": ts,
                "webhook-signature": _sign(webhook_id, ts, body),
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "event emission failed; will retry"
    emit.assert_awaited_once()
    mark_failed.assert_awaited_once_with(existing_id)


def test_formbricks_webhook_emits_pending_audited_retry(monkeypatch) -> None:
    monkeypatch.setenv("FORMBRICKS_WEBHOOK_SECRET", SECRET)
    webhook_id = "evt_retry_pending_test"
    body = _formbricks_body(webhook_id=webhook_id)
    ts = str(int(time.time()))
    existing_id = uuid4()

    with (
        patch(
            "form_receiver.api.capture_status_for_webhook",
            new=AsyncMock(
                return_value=CaptureWebhookStatus(
                    lead_id=existing_id,
                    event_status="pending",
                    audit_recorded=True,
                )
            ),
        ),
        patch("form_receiver.api.claim_capture_event_dispatch", new=AsyncMock(return_value=True)),
        patch("form_receiver.api._hatchet", object()),
        patch("form_receiver.api.emit_lead_captured", new=AsyncMock()) as emit,
        patch("form_receiver.api.mark_capture_event_emitted", new=AsyncMock()) as mark_emitted,
    ):
        response = TestClient(app).post(
            "/webhooks/formbricks",
            content=body,
            headers={
                "content-type": "application/json",
                "webhook-id": webhook_id,
                "webhook-timestamp": ts,
                "webhook-signature": _sign(webhook_id, ts, body),
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted-duplicate"}
    emit.assert_awaited_once()
    mark_emitted.assert_awaited_once_with(existing_id)


def test_formbricks_webhook_refills_missing_audit_before_retry_emit(monkeypatch) -> None:
    monkeypatch.setenv("FORMBRICKS_WEBHOOK_SECRET", SECRET)
    webhook_id = "evt_retry_missing_audit_test"
    body = _formbricks_body(webhook_id=webhook_id)
    ts = str(int(time.time()))
    existing_id = uuid4()

    with (
        patch(
            "form_receiver.api.capture_status_for_webhook",
            new=AsyncMock(
                return_value=CaptureWebhookStatus(
                    lead_id=existing_id,
                    event_status="pending",
                    audit_recorded=False,
                )
            ),
        ),
        patch("form_receiver.api.record_audit", new=AsyncMock(return_value=True)) as record_audit,
        patch("form_receiver.api.claim_capture_event_dispatch", new=AsyncMock(return_value=True)),
        patch("form_receiver.api._hatchet", object()),
        patch("form_receiver.api.emit_lead_captured", new=AsyncMock()),
        patch("form_receiver.api.mark_capture_event_emitted", new=AsyncMock()),
    ):
        response = TestClient(app).post(
            "/webhooks/formbricks",
            content=body,
            headers={
                "content-type": "application/json",
                "webhook-id": webhook_id,
                "webhook-timestamp": ts,
                "webhook-signature": _sign(webhook_id, ts, body),
            },
        )

    assert response.status_code == 200
    record_audit.assert_awaited_once()
