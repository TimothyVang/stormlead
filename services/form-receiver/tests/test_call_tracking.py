from __future__ import annotations

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, patch

import form_receiver.api as api
import pytest
from fastapi.testclient import TestClient
from form_receiver.api import app
from form_receiver.call_tracking import CallTrackingEvent, verify_call_tracking_signature
from form_receiver.signatures import InvalidSignatureError, ReplayError

CALL_TRACKING_TEST_KEY = "unit-test-call-tracking-key"


def _call_tracking_signature(secret: str, timestamp: str, body: bytes) -> str:
    sig = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"v1,{sig}"


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


def test_call_tracking_signature_validates() -> None:
    body = b'{"call_id":"test-001"}'
    timestamp = str(int(time.time()))
    verify_call_tracking_signature(
        raw_body=body,
        signature=_call_tracking_signature(CALL_TRACKING_TEST_KEY, timestamp, body),
        timestamp=timestamp,
        secret=CALL_TRACKING_TEST_KEY,
    )


def test_call_tracking_signature_rejects_replay() -> None:
    body = b"{}"
    timestamp = str(int(time.time()) - 600)
    with pytest.raises(ReplayError):
        verify_call_tracking_signature(
            raw_body=body,
            signature=_call_tracking_signature(CALL_TRACKING_TEST_KEY, timestamp, body),
            timestamp=timestamp,
            secret=CALL_TRACKING_TEST_KEY,
        )


def test_call_tracking_signature_rejects_mismatch() -> None:
    timestamp = str(int(time.time()))
    with pytest.raises(InvalidSignatureError):
        verify_call_tracking_signature(
            raw_body=b'{"call_id":"test-001"}',
            signature="v1," + ("0" * 64),
            timestamp=timestamp,
            secret=CALL_TRACKING_TEST_KEY,
        )


def test_call_tracking_requires_secret_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORMLEAD_ENV", "production")
    with pytest.raises(InvalidSignatureError):
        verify_call_tracking_signature(
            raw_body=b"{}",
            signature=None,
            timestamp=None,
            secret="",
        )


def test_call_tracking_endpoint_rejects_unsigned_production_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORMLEAD_ENV", "production")
    monkeypatch.setenv("CALL_TRACKING_WEBHOOK_SECRET", CALL_TRACKING_TEST_KEY)

    response = TestClient(app).post(
        "/webhooks/call-tracking",
        json={
            "call_id": "test-001",
            "phone_e164": "+13215550001",
            "outcome": "answered",
            "tracked_at": "2026-05-04T12:00:00Z",
        },
    )

    assert response.status_code == 401


def test_call_tracking_endpoint_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "MAX_WEBHOOK_BODY_BYTES", 16)
    response = TestClient(app).post(
        "/webhooks/call-tracking",
        content=b"{" + (b'"x":' + b'"' + (b"a" * 64) + b'"') + b"}",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413


def test_call_tracking_endpoint_rejects_replayed_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORMLEAD_ENV", "production")
    monkeypatch.setenv("CALL_TRACKING_WEBHOOK_SECRET", CALL_TRACKING_TEST_KEY)
    body = b'{"call_id":"test-001","phone_e164":"+13215550001","outcome":"answered","tracked_at":"2026-05-04T12:00:00Z"}'
    timestamp = str(int(time.time()) - 600)

    response = TestClient(app).post(
        "/webhooks/call-tracking",
        content=body,
        headers={
            "content-type": "application/json",
            "x-call-tracking-timestamp": timestamp,
            "x-call-tracking-signature": _call_tracking_signature(
                CALL_TRACKING_TEST_KEY, timestamp, body
            ),
        },
    )

    assert response.status_code == 409


def test_call_tracking_endpoint_persists_signed_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORMLEAD_ENV", "production")
    monkeypatch.setenv("CALL_TRACKING_WEBHOOK_SECRET", CALL_TRACKING_TEST_KEY)
    body = (
        b'{"call_id":"test-001","phone_e164":"+13215550001","outcome":"answered",'
        b'"tracked_at":"2026-05-04T12:00:00Z"}'
    )
    timestamp = str(int(time.time()))

    class SessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *args: object) -> None:
            return None

    with (
        patch("form_receiver.api.get_session", return_value=SessionContext()),
        patch(
            "form_receiver.api.ingest_call_event",
            new=AsyncMock(return_value={"call_id": "test-001", "matched": False}),
        ) as ingest,
    ):
        response = TestClient(app).post(
            "/webhooks/call-tracking",
            content=body,
            headers={
                "content-type": "application/json",
                "x-call-tracking-timestamp": timestamp,
                "x-call-tracking-signature": _call_tracking_signature(
                    CALL_TRACKING_TEST_KEY, timestamp, body
                ),
            },
        )

    assert response.status_code == 200
    ingest.assert_awaited_once()
