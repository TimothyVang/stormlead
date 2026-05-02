"""standard-webhooks signature verification.

reference: https://www.standardwebhooks.com/

formbricks emits these three headers per delivery:
  webhook-id         stable across retries; dedup key
  webhook-timestamp  unix seconds (string)
  webhook-signature  one or more space-separated `v1,<base64sig>` tuples
                     (multiple = key rotation; accept if *any* match)

algorithm:
  signed_payload = f"{id}.{ts}.{raw_body}"
  sig = base64(hmac_sha256(base64decode(secret.removeprefix("whsec_")), signed_payload))

constant-time compare; ±5-min replay window.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Final

REPLAY_WINDOW_S: Final = 5 * 60


class SignatureError(Exception):
    """raised when a webhook signature fails verification.

    distinct subclasses let api.py map to different http status codes:
      MissingHeaderError   → 400
      ReplayError          → 409
      InvalidSignatureError → 401
    """


class MissingHeaderError(SignatureError):
    pass


class ReplayError(SignatureError):
    pass


class InvalidSignatureError(SignatureError):
    pass


def _decode_secret(secret: str) -> bytes:
    """formbricks (standard-webhooks) secrets are `whsec_<base64>`."""
    body = secret.removeprefix("whsec_")
    # be tolerant of missing padding
    pad = "=" * (-len(body) % 4)
    return base64.b64decode(body + pad)


def verify(
    *,
    raw_body: bytes,
    webhook_id: str | None,
    webhook_timestamp: str | None,
    webhook_signature: str | None,
    secret: str,
    now_unix: int | None = None,
) -> None:
    """raise on missing headers, replay, or signature mismatch. else return."""
    if not (webhook_id and webhook_timestamp and webhook_signature):
        raise MissingHeaderError("missing standard-webhooks headers")

    try:
        ts = int(webhook_timestamp)
    except ValueError as e:
        raise MissingHeaderError("invalid webhook-timestamp") from e

    now = now_unix if now_unix is not None else int(time.time())
    if abs(now - ts) > REPLAY_WINDOW_S:
        raise ReplayError(f"timestamp outside ±{REPLAY_WINDOW_S}s window")

    secret_bytes = _decode_secret(secret)
    signed_payload = f"{webhook_id}.{webhook_timestamp}.".encode() + raw_body
    expected = base64.b64encode(
        hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()
    ).decode()

    # webhook-signature is space-separated `v1,<base64sig>` tuples (rotation).
    # accept if any matches; constant-time compare each.
    matched = False
    for part in webhook_signature.split(" "):
        if not part.startswith("v1,"):
            continue
        candidate = part.split(",", 1)[1]
        if hmac.compare_digest(candidate, expected):
            matched = True
            # do not break — keep the comparison time roughly constant
    if not matched:
        raise InvalidSignatureError("signature mismatch")
