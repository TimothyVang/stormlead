"""end-to-end smoke test for the validation-readiness phase.

assumes the pipeline dev stack is up + migrated + seeded:
  just up-pipeline   (postgres + hatchet + litellm + workflow services)
  just migrate       (0001_initial + 0002_consent_audits applied)
  just seed          (1 storm + 2 buyers + 1 lead with fixed UUIDs;
                      smoke-created buyers point at host.docker.internal:<port>/buyer-{a,b})

steps:
  1. start two in-process aiohttp listeners on an OS-assigned local port
     at /buyer-{a,b}
     to catch the auction's POST-to-winner webhooks from Docker containers.
  2. build a synthetic formbricks `responseFinished` envelope.
  3. sign it with FORMBRICKS_WEBHOOK_SECRET via the standard-webhooks algo.
  4. POST to http://localhost:8002/webhooks/formbricks; expect 200.
     form-receiver's 200 response carries the persisted lead_id, so no
     host-side postgres connection is needed (and avoids the
     remapped-host-port DSN dance).
  5. wait up to 30s for at least one buyer listener to receive a webhook.
  6. print structured result + exit 0; on any failure exit 1.

run: uv run python scripts/smoke_e2e.py
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse

import httpx
from aiohttp import web

LISTENER_PORT = int(os.environ.get("SMOKE_LISTENER_PORT", "0"))
LISTENER_HOST = os.environ.get("SMOKE_LISTENER_HOST", "0.0.0.0")  # noqa: S104 - Docker callback listener
SMOKE_TARGET_ZIP = os.environ.get("SMOKE_TARGET_ZIP", "78701")


def _is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _assert_loopback_http_url(label: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not _is_loopback_hostname(parsed.hostname):
        raise ValueError(f"{label} must be loopback HTTP(S), got {value}")
    return value


def _assert_local_buyer_callback_url(label: str, value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        _is_loopback_hostname(host) or host == "host.docker.internal"
    ):
        raise ValueError(f"{label} must stay local/host.docker.internal HTTP(S), got {value}")
    return value.rstrip("/")


FORM_RECEIVER_URL = _assert_loopback_http_url(
    "FORM_RECEIVER_URL",
    os.environ.get("FORM_RECEIVER_URL", "http://localhost:8002/webhooks/formbricks"),
)
CALL_TRACKING_URL = _assert_loopback_http_url(
    "CALL_TRACKING_URL",
    os.environ.get(
        "CALL_TRACKING_URL",
        FORM_RECEIVER_URL.replace("/webhooks/formbricks", "/webhooks/call-tracking"),
    ),
)
PING_POST_URL = _assert_loopback_http_url(
    "PING_POST_URL", os.environ.get("PING_POST_URL", "http://localhost:8003")
)
ACTIVE_LISTENER_PORT = LISTENER_PORT
SMOKE_BUYER_WEBHOOK_BASE = ""
ALLOWED_LISTENER_HOSTS: set[str] = set()
DOCKER_CALLBACK_NETWORKS = (
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.65.0/24"),
)


def _configure_listener_urls(port: int) -> None:
    global ACTIVE_LISTENER_PORT, SMOKE_BUYER_WEBHOOK_BASE, ALLOWED_LISTENER_HOSTS
    ACTIVE_LISTENER_PORT = port
    SMOKE_BUYER_WEBHOOK_BASE = _assert_local_buyer_callback_url(
        "SMOKE_BUYER_WEBHOOK_BASE",
        os.environ.get("SMOKE_BUYER_WEBHOOK_BASE", f"http://host.docker.internal:{port}"),
    )
    ALLOWED_LISTENER_HOSTS = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"host.docker.internal:{port}",
    }
    parsed = urlparse(SMOKE_BUYER_WEBHOOK_BASE)
    if parsed.netloc:
        ALLOWED_LISTENER_HOSTS.add(parsed.netloc.lower())


def _env_file_value(file_name: str, key: str) -> str | None:
    env_file = Path(file_name)
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


DEFAULT_SMOKE_SECRET = "whsec_" + base64.b64encode(b"smoke-test-secret-32-bytes-padded").decode()


def _candidate_secrets() -> list[str]:
    candidates = [
        os.environ.get("FORMBRICKS_WEBHOOK_SECRET"),
        _env_file_value(".env", "FORMBRICKS_WEBHOOK_SECRET"),
        _env_file_value(".env.example", "FORMBRICKS_WEBHOOK_SECRET"),
        DEFAULT_SMOKE_SECRET,
    ]
    unique = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


SYNTHETIC_PHONE = os.environ.get(
    "SMOKE_SYNTHETIC_PHONE",
    f"+1512{2000000 + (time.time_ns() % 8000000):07d}",
)

WEBHOOK_LISTENER_TIMEOUT_S = int(os.environ.get("SMOKE_WEBHOOK_LISTENER_TIMEOUT_S", "30"))


received: dict[str, list[dict[str, Any]]] = {"buyer-a": [], "buyer-b": []}


def _allowed_buyer_remote(remote: str | None) -> bool:
    if not remote:
        return False
    try:
        address = ipaddress.ip_address(remote.removeprefix("::ffff:"))
    except ValueError:
        return False
    return address.is_loopback or any(address in network for network in DOCKER_CALLBACK_NETWORKS)


def _allowed_buyer_request(request: web.Request) -> bool:
    host = request.headers.get("Host", "").lower()
    return host in ALLOWED_LISTENER_HOSTS and _allowed_buyer_remote(request.remote)


def _make_handler(name: str):
    async def handler(request: web.Request) -> web.Response:
        if not _allowed_buyer_request(request):
            return web.json_response({"error": "non_local_buyer_webhook_request"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid_json"}, status=400)
        received[name].append({"headers": dict(request.headers), "body": body})
        return web.json_response({"accept": True, "bid_cents": 5000})

    return handler


async def _start_listeners() -> web.AppRunner:
    app = web.Application()
    app.router.add_post("/buyer-a", _make_handler("buyer-a"))
    app.router.add_post("/buyer-b", _make_handler("buyer-b"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, LISTENER_HOST, LISTENER_PORT)
    await site.start()
    sockets = getattr(getattr(site, "_server", None), "sockets", None)
    actual_port = sockets[0].getsockname()[1] if sockets else LISTENER_PORT
    if not actual_port:
        raise RuntimeError("buyer listener did not expose a TCP port")
    _configure_listener_urls(int(actual_port))
    return runner


def _sign(secret: str, webhook_id: str, ts: str, body: bytes) -> str:
    raw = secret.removeprefix("whsec_")
    pad = "=" * (-len(raw) % 4)
    raw_secret = base64.b64decode(raw + pad)
    signed = f"{webhook_id}.{ts}.".encode() + body
    sig = base64.b64encode(hmac.new(raw_secret, signed, hashlib.sha256).digest()).decode()
    return f"v1,{sig}"


def _synthetic_envelope() -> dict[str, Any]:
    unique_id = time.time_ns()
    return {
        "event": "responseFinished",
        "webhookId": f"smoke-test-webhook-{unique_id}",
        "data": {
            "id": f"resp_{unique_id}",
            "surveyId": "survey_smoke",
            "data": {
                "name": "Smoke Test Homeowner",
                "phone": SYNTHETIC_PHONE,
                "email": "smoke@example.com",
                "address_line1": "999 Test Ln",
                "city": "Austin",
                "state": "TX",
                "zip": SMOKE_TARGET_ZIP,
                "consent_text": (
                    "I agree to be contacted by tree-removal contractors regarding storm damage."
                ),
                "page_html_sha256": hashlib.sha256(str(time.time()).encode()).hexdigest(),
                "requested_service": "tree_removal",
                "damage_type": "fallen_tree",
                "urgency": "same_day",
                "damage_description": "Synthetic fallen tree across the driveway with no reported power lines or injuries.",
                "power_line_involved": "false",
                "injury_reported": "false",
                "active_danger": "false",
                "campaign_id": "smoke-austin-v1",
                "campaign_source": "local_smoke",
                "first_touch_source": "local_smoke",
                "last_touch_source": "local_smoke",
                "gps_latitude": "30.4515",
                "gps_longitude": "-91.1871",
                "gps_accuracy_meters": "22",
                "gps_captured_at": datetime.now(UTC).isoformat(),
                "location_source": "browser_gps",
                "location_confirmed_at": datetime.now(UTC).isoformat(),
                "damage_photo_keys": '["wide.jpg", "close.jpg"]',
            },
            "ttc": {"name": 1500, "phone": 2200, "consent_text": 4500},
            "meta": {
                "url": "http://localhost:3000/austin-tx-tree-removal",
                "userAgent": "Mozilla/5.0 (smoke-test)",
            },
            "finished": True,
        },
    }


def _smoke_buyer_payload(name: str, webhook_path: str, unique_id: int) -> dict[str, Any]:
    if not SMOKE_BUYER_WEBHOOK_BASE:
        raise RuntimeError("buyer webhook listener base URL is not configured")
    return {
        "name": f"Smoke {name} Buyer",
        "company": f"Smoke {name} Tree Pros {unique_id}",
        "contact_email": f"smoke-{name.lower()}-{unique_id}@example-stormlead-test.com",
        "contact_phone_e164": f"+1512{3000000 + (unique_id % 6000000):07d}",
        "webhook_url": f"{SMOKE_BUYER_WEBHOOK_BASE}/{webhook_path}",
        "webhook_secret": f"smoke-{name.lower()}-webhook-secret",
        "bid_per_lead_t1_t2": "75.00",
        "bid_per_lead_t3": "175.00",
        "bid_per_call": "100.00",
        "filter_expression": "lead.state == 'TX'",
        "daily_cap": 25,
        "monthly_budget": "5000.00",
        "deposit_balance": "1000.00",
        "sales_stage": "funded",
        "notes": "Synthetic smoke buyer created by scripts/smoke_e2e.py for local-only verification.",
        "services": ["tree_removal"],
        "target_zips": [SMOKE_TARGET_ZIP],
        "low_balance_threshold": "150.00",
    }


async def _ensure_smoke_buyers(client: httpx.AsyncClient) -> list[str]:
    buyer_ids: list[str] = []
    unique_id = time.time_ns() % 10_000_000
    for offset, (name, path_suffix) in enumerate((("A", "buyer-a"), ("B", "buyer-b"))):
        payload = _smoke_buyer_payload(name, path_suffix, unique_id + offset)
        response = await client.post(f"{PING_POST_URL}/v1/buyers", json=payload)
        if response.status_code != 200:
            _fail("seed-smoke-buyers", f"status={response.status_code} body={response.text}")
        buyer = response.json()
        buyer_id = buyer.get("buyer_id")
        if not buyer_id:
            _fail("seed-smoke-buyers", f"missing buyer_id: {buyer}")
        activate_response = await client.patch(
            f"{PING_POST_URL}/v1/buyers/{buyer_id}",
            json={
                "status": "active",
                "sales_stage": "funded",
                "notes": payload["notes"],
            },
        )
        if activate_response.status_code != 200:
            _fail(
                "activate-smoke-buyers",
                f"buyer_id={buyer_id} status={activate_response.status_code} body={activate_response.text}",
            )
        buyer_ids.append(str(buyer_id))
    return buyer_ids


def _hits_for_lead(lead_id: str) -> list[dict[str, Any]]:
    return [
        hit for hits in received.values() for hit in hits if hit["body"].get("lead_id") == lead_id
    ]


async def _wait_for_buyer_hit(lead_id: str, timeout_s: int = WEBHOOK_LISTENER_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _hits_for_lead(lead_id):
            return True
        await asyncio.sleep(0.25)
    return False


def _post_hits(lead_id: str) -> list[dict[str, Any]]:
    return [
        hit
        for hits in received.values()
        for hit in hits
        if hit["headers"].get("X-Stormlead-Mode") == "post"
        and hit["body"].get("lead_id") == lead_id
    ]


async def _wait_for_buyer_post(
    lead_id: str,
    timeout_s: int = WEBHOOK_LISTENER_TIMEOUT_S,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hits = _post_hits(lead_id)
        if hits:
            return hits[0]
        await asyncio.sleep(0.25)
    return None


def _step(name: str) -> None:
    print(f"[smoke] {name} … ", end="", flush=True)


def _ok(detail: str = "") -> None:
    print(f"OK {detail}".rstrip())


def _fail(name: str, detail: str) -> NoReturn:
    print(f"FAIL: {name}\n  {detail}", file=sys.stderr)
    sys.exit(1)


async def main() -> None:
    started = time.perf_counter()

    _step("starting in-process buyer listeners")
    runner = await _start_listeners()
    _ok(f"{LISTENER_HOST}:{ACTIVE_LISTENER_PORT}")

    lead_id: str | None = None
    try:
        _step("posting synthetic formbricks webhook")
        body = json.dumps(_synthetic_envelope()).encode()
        # unique per run so consent_audits dedup doesn't suppress emission
        webhook_id = f"smoke-test-webhook-{int(time.time())}"
        ts = str(int(time.time()))
        async with httpx.AsyncClient(timeout=15) as client:
            _step(f"ensuring synthetic buyer coverage for {SMOKE_TARGET_ZIP}")
            buyer_ids = await _ensure_smoke_buyers(client)
            _ok(",".join(buyer_id[:8] for buyer_id in buyer_ids))

        async with httpx.AsyncClient(timeout=15) as client:
            r: httpx.Response | None = None
            for secret in _candidate_secrets():
                sig = _sign(secret, webhook_id, ts, body)
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
                if r.status_code != 401 or "signature mismatch" not in r.text:
                    break
        if r is None:
            _fail("post-webhook", "no Formbricks signing secrets were available")
        if r.status_code != 200:
            _fail("post-webhook", f"status={r.status_code} body={r.text}")
        payload = r.json()
        lead_id = payload.get("lead_id")
        if not lead_id:
            _fail("post-webhook", f"200 but no lead_id in body: {payload}")
        _ok(f"status={payload.get('status')} lead_id={lead_id}")

        async with httpx.AsyncClient(timeout=15) as client:
            _step("posting synthetic call-tracking webhook")
            call_response = await client.post(
                CALL_TRACKING_URL,
                json={
                    "call_id": f"smoke-call-{int(time.time())}",
                    "phone_e164": SYNTHETIC_PHONE,
                    "duration_seconds": 91,
                    "outcome": "answered",
                    "tracked_at": datetime.now(UTC).isoformat(),
                    "raw_payload": {"source": "local_smoke", "synthetic_only": True},
                },
            )
            if call_response.status_code != 200:
                _fail(
                    "call-tracking-webhook",
                    f"status={call_response.status_code} body={call_response.text}",
                )
            call_payload = call_response.json()
            if call_payload.get("lead_id") != lead_id:
                _fail("call-tracking-webhook", f"call did not match lead: {call_payload}")
            _ok(f"event_id={call_payload.get('event_id')}")

        _step(f"waiting for buyer ping webhook (max {WEBHOOK_LISTENER_TIMEOUT_S}s)")
        ping_hit = await _wait_for_buyer_hit(lead_id)
        if not ping_hit:
            _fail(
                "buyer-ping-webhook",
                f"neither buyer-a nor buyer-b received a webhook within "
                f"{WEBHOOK_LISTENER_TIMEOUT_S}s — check ping-post worker, "
                f"agent-runtime QualifyLead workflow, hatchet engine logs",
            )
        which = ", ".join(k for k, v in received.items() if v)
        _ok(f"hit by: {which}")

        _step(f"waiting for winning buyer post (max {WEBHOOK_LISTENER_TIMEOUT_S}s)")
        post_hit = await _wait_for_buyer_post(lead_id)
        if post_hit is None:
            _fail(
                "buyer-post-webhook",
                "buyer ping occurred but no X-Stormlead-Mode=post delivery arrived",
            )
        post_body = post_hit["body"]
        post_idempotency_key = post_hit["headers"].get("Idempotency-Key")
        if not post_idempotency_key:
            _fail("buyer-post-webhook", "post delivery did not include Idempotency-Key")
        _ok(f"idempotency_key={post_idempotency_key[:12]}...")

        async with httpx.AsyncClient(timeout=15) as client:
            _step("requesting invalid-lead return review")
            return_response = await client.post(
                f"{PING_POST_URL}/v1/leads/{lead_id}/return",
                json={
                    "reason": "duplicate",
                    "notes": "Smoke test return request; local validation only.",
                    "evidence": {"buyer_delivery_lead_id": post_body.get("lead_id")},
                    "requested_by": "smoke-test-buyer",
                },
            )
            if return_response.status_code != 200:
                _fail(
                    "return-request",
                    f"status={return_response.status_code} body={return_response.text}",
                )
            return_payload = return_response.json()
            return_request_id = return_payload.get("return_request_id")
            if not return_request_id:
                _fail("return-request", f"missing return_request_id: {return_payload}")
            _ok(f"return_request_id={return_request_id}")

            _step("approving return request and credit saga")
            review_response = await client.post(
                f"{PING_POST_URL}/v1/return-requests/{return_request_id}/review",
                json={
                    "action": "approve",
                    "notes": "Approved by smoke test to validate credit audit path.",
                    "operator": "smoke-e2e",
                },
            )
            if review_response.status_code != 200:
                _fail(
                    "return-review",
                    f"status={review_response.status_code} body={review_response.text}",
                )
            review_payload = review_response.json()
            buyer_id = review_payload.get("buyer_id")
            credited_cents = review_payload.get("credited_cents")
            if not buyer_id or not credited_cents:
                _fail("return-review", f"missing buyer_id/credited_cents: {review_payload}")
            _ok(f"buyer_id={buyer_id} credited_cents={credited_cents}")

            _step("loading buyer daily report")
            report_response = await client.get(f"{PING_POST_URL}/v1/buyers/{buyer_id}/daily-report")
            if report_response.status_code != 200:
                _fail(
                    "buyer-daily-report",
                    f"status={report_response.status_code} body={report_response.text}",
                )
            report_payload = report_response.json()
            if report_payload["delivery"]["pending_return_requests"] != 0:
                _fail("buyer-daily-report", f"return request still pending: {report_payload}")
            _ok("report loaded")

            _step("loading admin lead timeline")
            timeline_response = await client.get(
                f"{PING_POST_URL}/v1/admin/leads/{lead_id}/timeline"
            )
            if timeline_response.status_code != 200:
                _fail(
                    "admin-timeline",
                    f"status={timeline_response.status_code} body={timeline_response.text}",
                )
            event_types = [
                event["event_type"] for event in timeline_response.json().get("events", [])
            ]
            for required in {
                "lead.captured",
                "lead.sold",
                "lead.return_requested",
                "lead.return_approved",
            }:
                if required not in event_types:
                    _fail("admin-timeline", f"missing {required}; event_types={event_types}")
            _ok(f"events={len(event_types)}")

            _step("checking scoped launch-readiness endpoint")
            readiness_response = await client.get(
                f"{PING_POST_URL}/v1/admin/launch-readiness",
                params={
                    "market_zip": "78701",
                    "service": "tree_removal",
                    "campaign_budget_cents": 1000,
                },
            )
            if readiness_response.status_code != 200:
                _fail(
                    "launch-readiness",
                    f"status={readiness_response.status_code} body={readiness_response.text}",
                )
            readiness_payload = readiness_response.json()
            if "technical_local_ready" not in readiness_payload:
                _fail("launch-readiness", f"unexpected response: {readiness_payload}")
            _ok(f"label={readiness_payload.get('readiness_label')}")

    finally:
        await runner.cleanup()

    duration_ms = int((time.perf_counter() - started) * 1000)
    print(f"\n[smoke] PASS in {duration_ms}ms")
    print(f"  lead_id      = {lead_id}")
    print(f"  buyer-a hits = {len(received['buyer-a'])}")
    print(f"  buyer-b hits = {len(received['buyer-b'])}")


if __name__ == "__main__":
    asyncio.run(main())
