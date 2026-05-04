"""unit tests for standard-webhooks signature verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest
from form_receiver.signatures import (
    InvalidSignatureError,
    MissingHeaderError,
    ReplayError,
    verify,
)

SECRET = "whsec_" + base64.b64encode(b"unit-test-secret-32-bytes-padded!").decode()


def _sign(webhook_id: str, ts: str, body: bytes, secret: str = SECRET) -> str:
    raw_secret = base64.b64decode(secret.removeprefix("whsec_") + "==")
    signed = f"{webhook_id}.{ts}.".encode() + body
    sig = base64.b64encode(hmac.new(raw_secret, signed, hashlib.sha256).digest()).decode()
    return f"v1,{sig}"


def test_valid_signature_passes() -> None:
    body = b'{"event":"responseFinished","webhookId":"abc","data":{}}'
    ts = str(int(time.time()))
    sig = _sign("evt_1", ts, body)
    verify(
        raw_body=body,
        webhook_id="evt_1",
        webhook_timestamp=ts,
        webhook_signature=sig,
        secret=SECRET,
    )  # no raise


def test_missing_headers_raise() -> None:
    with pytest.raises(MissingHeaderError):
        verify(
            raw_body=b"{}",
            webhook_id=None,
            webhook_timestamp="0",
            webhook_signature="v1,xxx",
            secret=SECRET,
        )


def test_invalid_timestamp_raises() -> None:
    with pytest.raises(MissingHeaderError):
        verify(
            raw_body=b"{}",
            webhook_id="evt_1",
            webhook_timestamp="not-a-number",
            webhook_signature="v1,xxx",
            secret=SECRET,
        )


def test_replay_outside_window_raises() -> None:
    body = b"{}"
    old_ts = str(int(time.time()) - 10 * 60)  # 10 min ago
    sig = _sign("evt_1", old_ts, body)
    with pytest.raises(ReplayError):
        verify(
            raw_body=body,
            webhook_id="evt_1",
            webhook_timestamp=old_ts,
            webhook_signature=sig,
            secret=SECRET,
        )


def test_wrong_signature_raises() -> None:
    body = b"{}"
    ts = str(int(time.time()))
    bad_sig = "v1," + base64.b64encode(b"x" * 32).decode()
    with pytest.raises(InvalidSignatureError):
        verify(
            raw_body=body,
            webhook_id="evt_1",
            webhook_timestamp=ts,
            webhook_signature=bad_sig,
            secret=SECRET,
        )


def test_multi_signature_one_valid_passes() -> None:
    """key rotation: sigs are space-separated; any match passes."""
    body = b"{}"
    ts = str(int(time.time()))
    good_sig = _sign("evt_1", ts, body)
    bad_sig = "v1," + base64.b64encode(b"x" * 32).decode()
    combined = f"{bad_sig} {good_sig}"
    verify(
        raw_body=body,
        webhook_id="evt_1",
        webhook_timestamp=ts,
        webhook_signature=combined,
        secret=SECRET,
    )  # no raise


def test_body_mutation_breaks_signature() -> None:
    body = b'{"a":1}'
    ts = str(int(time.time()))
    sig = _sign("evt_1", ts, body)
    mutated = b'{"a":2}'
    with pytest.raises(InvalidSignatureError):
        verify(
            raw_body=mutated,
            webhook_id="evt_1",
            webhook_timestamp=ts,
            webhook_signature=sig,
            secret=SECRET,
        )
