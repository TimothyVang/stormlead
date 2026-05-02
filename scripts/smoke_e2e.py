"""end-to-end smoke test for the validation-readiness phase.

assumes the full dev stack is up + migrated + seeded:
  just up            (postgres + redis + hatchet + litellm + python services)
  just migrate       (0001_initial + 0002_consent_audits applied)
  just seed          (1 storm + 2 buyers + 1 lead with fixed UUIDs;
                      buyers point at host.docker.internal:9999/buyer-{a,b})

steps:
  1. start two in-process aiohttp listeners on localhost:9999/buyer-{a,b}
     to catch the auction's POST-to-winner webhooks.
  2. build a synthetic formbricks `responseFinished` envelope.
  3. sign it with FORMBRICKS_WEBHOOK_SECRET via the standard-webhooks algo.
  4. POST to http://localhost:8002/webhooks/formbricks; expect 200.
     form-receiver's 200 response carries the persisted lead_id, so no
     host-side postgres connection is needed (and avoids the
     remapped-host-port DSN dance).
  5. wait up to 10s for at least one buyer listener to receive a webhook.
  6. print structured result + exit 0; on any failure exit 1.

run: uv run python scripts/smoke_e2e.py
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from typing import Any

import httpx
from aiohttp import web


FORM_RECEIVER_URL = os.environ.get(
    "FORM_RECEIVER_URL", "http://localhost:8002/webhooks/formbricks"
)
LISTENER_PORT = 9999
SECRET = os.environ.get(
    "FORMBRICKS_WEBHOOK_SECRET",
    "whsec_" + base64.b64encode(b"smoke-test-secret-32-bytes-padded").decode(),
)
SYNTHETIC_PHONE = "+15125550199"  # distinct from the seed lead's +15125550100

WEBHOOK_LISTENER_TIMEOUT_S = 10


received: dict[str, list[dict[str, Any]]] = {"buyer-a": [], "buyer-b": []}


def _make_handler(name: str):
    async def handler(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        received[name].append({"headers": dict(request.headers), "body": body})
        return web.json_response({"accepted": True, "bid_cents": 5000})

    return handler


async def _start_listeners() -> web.AppRunner:
    app = web.Application()
    app.router.add_post("/buyer-a", _make_handler("buyer-a"))
    app.router.add_post("/buyer-b", _make_handler("buyer-b"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", LISTENER_PORT)
    await site.start()
    return runner


def _sign(webhook_id: str, ts: str, body: bytes) -> str:
    raw = SECRET.removeprefix("whsec_")
    pad = "=" * (-len(raw) % 4)
    raw_secret = base64.b64decode(raw + pad)
    signed = f"{webhook_id}.{ts}.".encode() + body
    sig = base64.b64encode(
        hmac.new(raw_secret, signed, hashlib.sha256).digest()
    ).decode()
    return f"v1,{sig}"


def _synthetic_envelope() -> dict[str, Any]:
    return {
        "event": "responseFinished",
        "webhookId": "smoke-test-webhook",
        "data": {
            "id": f"resp_{int(time.time())}",
            "surveyId": "survey_smoke",
            "data": {
                "name": "Smoke Test Homeowner",
                "phone": SYNTHETIC_PHONE,
                "email": "smoke@example.com",
                "address_line1": "999 Test Ln",
                "city": "Austin",
                "state": "TX",
                "zip": "78701",
                "consent_text": (
                    "I agree to be contacted by tree-removal contractors "
                    "regarding storm damage."
                ),
                "page_html_sha256": "1" * 64,
            },
            "ttc": {"name": 1500, "phone": 2200, "consent_text": 4500},
            "meta": {
                "url": "http://localhost:3000/austin-tx-tree-removal",
                "userAgent": "Mozilla/5.0 (smoke-test)",
            },
            "finished": True,
        },
    }


async def _wait_for_buyer_hit(timeout_s: int = WEBHOOK_LISTENER_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if received["buyer-a"] or received["buyer-b"]:
            return True
        await asyncio.sleep(0.25)
    return False


def _step(name: str) -> None:
    print(f"[smoke] {name} … ", end="", flush=True)


def _ok(detail: str = "") -> None:
    print(f"OK {detail}".rstrip())


def _fail(name: str, detail: str) -> None:
    print(f"FAIL: {name}\n  {detail}", file=sys.stderr)
    sys.exit(1)


async def main() -> None:
    started = time.perf_counter()

    _step("starting in-process buyer listeners")
    runner = await _start_listeners()
    _ok(f"port {LISTENER_PORT}")

    lead_id: str | None = None
    try:
        _step("posting synthetic formbricks webhook")
        body = json.dumps(_synthetic_envelope()).encode()
        # unique per run so consent_audits dedup doesn't suppress emission
        webhook_id = f"smoke-test-webhook-{int(time.time())}"
        ts = str(int(time.time()))
        sig = _sign(webhook_id, ts, body)
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                FORM_RECEIVER_URL,
                content=body,
                headers={
                    "content-type": "application/json",
                    "webhook-id": webhook_id,
                    "webhook-timestamp": ts,
                    "webhook-signature": sig,
                },
            )
        if r.status_code != 200:
            _fail("post-webhook", f"status={r.status_code} body={r.text}")
        payload = r.json()
        lead_id = payload.get("lead_id")
        if not lead_id:
            _fail("post-webhook", f"200 but no lead_id in body: {payload}")
        _ok(f"status={payload.get('status')} lead_id={lead_id}")

        _step(f"waiting for buyer webhook (max {WEBHOOK_LISTENER_TIMEOUT_S}s)")
        hit = await _wait_for_buyer_hit()
        if not hit:
            _fail(
                "buyer-webhook",
                f"neither buyer-a nor buyer-b received a webhook within "
                f"{WEBHOOK_LISTENER_TIMEOUT_S}s — check ping-post worker, "
                f"agent-runtime QualifyLead workflow, hatchet engine logs",
            )
        which = ", ".join(k for k, v in received.items() if v)
        _ok(f"hit by: {which}")

    finally:
        await runner.cleanup()

    duration_ms = int((time.perf_counter() - started) * 1000)
    print(f"\n[smoke] PASS in {duration_ms}ms")
    print(f"  lead_id      = {lead_id}")
    print(f"  buyer-a hits = {len(received['buyer-a'])}")
    print(f"  buyer-b hits = {len(received['buyer-b'])}")


if __name__ == "__main__":
    asyncio.run(main())
