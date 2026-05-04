"""Run the V1 local simulation scenarios and write an evidence manifest.

The harness uses the same public local HTTP boundaries as the smoke test:
signed Formbricks webhooks enter through form-receiver, auctions run through
Hatchet workers, and return/review/readiness checks go through ping-post APIs.
Database reads are evidence collection only.

Run: uv run python scripts/simulate_v1_leads.py
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from aiohttp import web
from seed_dev import _seed
from sqlalchemy import func, select
from stormlead_db import (
    ConsentAudit,
    LeadRow,
    LeadStateTransition,
    PingAttempt,
    PostResult,
    ReturnRequest,
    get_session,
)

FORM_RECEIVER_URL = os.environ.get(
    "FORM_RECEIVER_URL", "http://localhost:8002/webhooks/formbricks"
)
FORM_RECEIVER_BASE_URL = os.environ.get("FORM_RECEIVER_BASE_URL", "http://localhost:8002")
PING_POST_URL = os.environ.get("PING_POST_URL", "http://localhost:8003")
LISTENER_HOST = os.environ.get("SIM_LISTENER_HOST", "127.0.0.1")
LISTENER_PORT = int(os.environ.get("SIM_LISTENER_PORT", "9999"))
WORKFLOW_TIMEOUT_S = int(os.environ.get("SIM_WORKFLOW_TIMEOUT_S", "45"))

DEFAULT_WEBHOOK_SECRET = "whsec_" + base64.b64encode(
    b"smoke-test-secret-32-bytes-padded"
).decode()

BUYER_HITS: list[dict[str, Any]] = []


def _env_file_value(file_name: str, key: str) -> str | None:
    env_file = Path(file_name)
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _configure_database_url() -> None:
    if os.environ.get("DATABASE_URL"):
        return
    host_url = _env_file_value(".env", "DATABASE_URL_HOST") or _env_file_value(
        ".env.example", "DATABASE_URL_HOST"
    )
    if host_url:
        os.environ["DATABASE_URL"] = host_url


def _candidate_secrets() -> list[str]:
    candidates = [
        os.environ.get("FORMBRICKS_WEBHOOK_SECRET"),
        _env_file_value(".env", "FORMBRICKS_WEBHOOK_SECRET"),
        _env_file_value(".env.example", "FORMBRICKS_WEBHOOK_SECRET"),
        DEFAULT_WEBHOOK_SECRET,
    ]
    unique = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def _sign(secret: str, webhook_id: str, ts: str, body: bytes) -> str:
    raw = secret.removeprefix("whsec_")
    pad = "=" * (-len(raw) % 4)
    raw_secret = base64.b64decode(raw + pad)
    signed = f"{webhook_id}.{ts}.".encode() + body
    sig = base64.b64encode(hmac.new(raw_secret, signed, hashlib.sha256).digest()).decode()
    return f"v1,{sig}"


async def _buyer_handler(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    mode = request.headers.get("X-Stormlead-Mode", "unknown")
    BUYER_HITS.append(
        {
            "path": request.path,
            "mode": mode,
            "lead_id": body.get("lead_id"),
            "state": body.get("state"),
            "zip": body.get("zip"),
            "bid_cents": body.get("purchase", {}).get("bid_cents"),
            "idempotency_key_present": bool(request.headers.get("Idempotency-Key")),
        }
    )
    if mode == "ping":
        return web.json_response({"accept": True, "bid_cents": 5000})
    return web.json_response({"accepted": True})


async def _start_buyer_listener() -> web.AppRunner:
    app = web.Application()
    app.router.add_post("/{tail:.*}", _buyer_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, LISTENER_HOST, LISTENER_PORT)
    await site.start()
    return runner


def _phone(run_seed: int, offset: int) -> str:
    prefix = 600 + ((run_seed + offset) % 300)
    line = 1000 + offset
    return f"+1512{prefix:03d}{line:04d}"


def _page_hash(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


def _envelope(
    *,
    scenario: str,
    run_id: str,
    phone: str,
    email: str,
    state: str,
    zip_code: str,
    campaign_id: str,
    campaign_source: str = "v1-simulation",
    page_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "event": "responseFinished",
        "webhookId": f"v1-simulation-{scenario}",
        "data": {
            "id": f"resp_{scenario}_{uuid4().hex[:12]}",
            "surveyId": "survey_v1_simulation",
            "data": {
                "name": f"Synthetic {scenario}",
                "phone": phone,
                "email": email,
                "address_line1": "999 Simulation Ln",
                "city": "Austin" if state == "TX" else "Atlanta",
                "state": state,
                "zip": zip_code,
                "consent_text": (
                    "I agree to be contacted by tree-removal contractors regarding storm damage."
                ),
                "page_html_sha256": page_hash or _page_hash(run_id, scenario, phone),
                "dwell_ms": 9000,
                "requested_service": "tree_removal",
                "campaign_id": campaign_id,
                "campaign_source": campaign_source,
                "first_touch_source": campaign_source,
                "last_touch_source": campaign_source,
            },
            "ttc": {"name": 1500, "phone": 2200, "consent_text": 4500},
            "meta": {
                "url": f"http://localhost:3000/{scenario}-tree-removal",
                "userAgent": "Mozilla/5.0 (v1-local-simulation)",
            },
            "finished": True,
        },
    }


async def _post_webhook(
    client: httpx.AsyncClient, envelope: dict[str, Any], webhook_id: str
) -> httpx.Response:
    body = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
    ts = str(int(time.time()))
    response: httpx.Response | None = None
    for secret in _candidate_secrets():
        response = await client.post(
            FORM_RECEIVER_URL,
            content=body,
            headers={
                "content-type": "application/json",
                "webhook-id": webhook_id,
                "webhook-timestamp": ts,
                "webhook-signature": _sign(secret, webhook_id, ts, body),
            },
        )
        if response.status_code != 401 or "signature mismatch" not in response.text:
            break
    if response is None:
        raise RuntimeError("no Formbricks signing secrets were available")
    return response


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(f"response was not JSON: status={response.status_code}") from e
    if not isinstance(data, dict):
        raise RuntimeError(f"response JSON was not an object: {data}")
    return data


async def _submit_lead(
    client: httpx.AsyncClient,
    *,
    scenario: str,
    run_id: str,
    phone: str,
    email: str,
    state: str,
    zip_code: str,
    campaign_id: str,
    webhook_id: str | None = None,
    page_hash: str | None = None,
) -> dict[str, Any]:
    envelope = _envelope(
        scenario=scenario,
        run_id=run_id,
        phone=phone,
        email=email,
        state=state,
        zip_code=zip_code,
        campaign_id=campaign_id,
        page_hash=page_hash,
    )
    response = await _post_webhook(
        client, envelope, webhook_id or f"v1-simulation-{scenario}-{uuid4()}"
    )
    if response.status_code != 200:
        raise RuntimeError(f"{scenario}: webhook failed {response.status_code}: {response.text}")
    return _json(response)


async def _wait_for_transition(
    lead_id: str, event_type: str, *, timeout_s: int = WORKFLOW_TIMEOUT_S
) -> LeadStateTransition:
    deadline = time.monotonic() + timeout_s
    parsed_id = UUID(lead_id)
    while time.monotonic() < deadline:
        async with get_session() as s:
            row = (
                (
                    await s.execute(
                        select(LeadStateTransition)
                        .where(
                            LeadStateTransition.lead_id == parsed_id,
                            LeadStateTransition.event_type == event_type,
                        )
                        .order_by(LeadStateTransition.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            if row is not None:
                return row
        await asyncio.sleep(0.5)
    raise TimeoutError(f"lead {lead_id} did not reach {event_type} within {timeout_s}s")


async def _wait_for_post(lead_id: str, *, timeout_s: int = WORKFLOW_TIMEOUT_S) -> PostResult:
    deadline = time.monotonic() + timeout_s
    parsed_id = UUID(lead_id)
    while time.monotonic() < deadline:
        async with get_session() as s:
            row = (
                (
                    await s.execute(
                        select(PostResult)
                        .where(PostResult.lead_id == parsed_id, PostResult.delivered.is_(True))
                        .order_by(PostResult.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            if row is not None:
                return row
        await asyncio.sleep(0.5)
    raise TimeoutError(f"lead {lead_id} was not delivered within {timeout_s}s")


async def _lead_evidence(lead_id: str) -> dict[str, Any]:
    parsed_id = UUID(lead_id)
    async with get_session() as s:
        lead = await s.get(LeadRow, parsed_id)
        if lead is None:
            raise RuntimeError(f"lead {lead_id} not found")
        transitions = (
            (
                await s.execute(
                    select(LeadStateTransition)
                    .where(LeadStateTransition.lead_id == parsed_id)
                    .order_by(LeadStateTransition.created_at)
                )
            )
            .scalars()
            .all()
        )
        pings = (
            (
                await s.execute(
                    select(PingAttempt)
                    .where(PingAttempt.lead_id == parsed_id)
                    .order_by(PingAttempt.created_at)
                )
            )
            .scalars()
            .all()
        )
        posts = (
            (
                await s.execute(
                    select(PostResult)
                    .where(PostResult.lead_id == parsed_id)
                    .order_by(PostResult.created_at)
                )
            )
            .scalars()
            .all()
        )
        returns = (
            (
                await s.execute(
                    select(ReturnRequest)
                    .where(ReturnRequest.lead_id == parsed_id)
                    .order_by(ReturnRequest.created_at)
                )
            )
            .scalars()
            .all()
        )
    return {
        "lead_id": lead_id,
        "lead": {
            "status": lead.status,
            "state": lead.state,
            "zip": lead.zip,
            "requested_service": lead.requested_service,
            "campaign_source": lead.campaign_source,
            "campaign_id": lead.campaign_id,
            "qualification_score": lead.qualification_score,
            "lead_class": lead.lead_class,
            "blocked_for_fraud": lead.blocked_for_fraud,
            "hold_for_review": lead.hold_for_review,
            "rejection_reason": lead.rejection_reason,
        },
        "transitions": [
            {
                "event_type": row.event_type,
                "from_state": row.from_state,
                "to_state": row.to_state,
                "status": row.status,
                "payload": row.payload_json,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in transitions
        ],
        "pings": [
            {
                "buyer_id": str(row.buyer_id),
                "accepted": row.accepted,
                "bid_cents": row.bid_cents,
                "status_code": row.response_status_code,
                "error": row.error,
            }
            for row in pings
        ],
        "posts": [
            {
                "buyer_id": str(row.buyer_id),
                "bid_cents": row.bid_cents,
                "delivered": row.delivered,
                "returned": row.returned,
                "idempotency_key_present": bool(row.delivery_idempotency_key),
            }
            for row in posts
        ],
        "returns": [
            {
                "return_request_id": str(row.id),
                "buyer_id": str(row.buyer_id),
                "reason": row.reason,
                "status": row.status,
                "reviewed_by": row.reviewed_by,
            }
            for row in returns
        ],
    }


async def _lead_count_for(phone: str, page_hash: str) -> int:
    async with get_session() as s:
        count = await s.scalar(
            select(func.count(LeadRow.id)).where(
                LeadRow.phone_e164 == phone,
                LeadRow.page_html_hash == page_hash,
            )
        )
    return int(count or 0)


async def _audit_count_for(webhook_id: str) -> int:
    async with get_session() as s:
        count = await s.scalar(
            select(func.count(ConsentAudit.webhook_id)).where(ConsentAudit.webhook_id == webhook_id)
        )
    return int(count or 0)


def _hits_for_lead(lead_id: str) -> list[dict[str, Any]]:
    return [hit for hit in BUYER_HITS if hit.get("lead_id") == lead_id]


async def _scenario_qualified_sold(
    client: httpx.AsyncClient, run_id: str, run_seed: int
) -> dict[str, Any]:
    payload = await _submit_lead(
        client,
        scenario="qualified_sold",
        run_id=run_id,
        phone=_phone(run_seed, 1),
        email=f"qualified-sold-{run_id}@example.com",
        state="TX",
        zip_code="78701",
        campaign_id="v1-simulation-qualified-sold",
    )
    lead_id = str(payload["lead_id"])
    await _wait_for_transition(lead_id, "lead.sold")
    await _wait_for_post(lead_id)
    return {
        "scenario": "qualified_sold",
        "status": "passed",
        "webhook_response": payload,
        "buyer_hits": _hits_for_lead(lead_id),
        "evidence": await _lead_evidence(lead_id),
    }


async def _scenario_returned_approved(
    client: httpx.AsyncClient, run_id: str, run_seed: int
) -> dict[str, Any]:
    payload = await _submit_lead(
        client,
        scenario="returned_approved",
        run_id=run_id,
        phone=_phone(run_seed, 2),
        email=f"returned-approved-{run_id}@example.com",
        state="TX",
        zip_code="78701",
        campaign_id="v1-simulation-returned-approved",
    )
    lead_id = str(payload["lead_id"])
    post = await _wait_for_post(lead_id)
    return_response = await client.post(
        f"{PING_POST_URL}/v1/leads/{lead_id}/return",
        json={
            "reason": "duplicate",
            "notes": "V1 local simulation return request; no real buyer contact.",
            "evidence": {"post_result_id": str(post.id)},
            "requested_by": "v1-simulation-buyer",
        },
    )
    if return_response.status_code != 200:
        raise RuntimeError(f"returned_approved: return failed {return_response.text}")
    return_payload = _json(return_response)
    review_response = await client.post(
        f"{PING_POST_URL}/v1/return-requests/{return_payload['return_request_id']}/review",
        json={
            "action": "approve",
            "notes": "Approved by V1 local simulation to validate wallet credit audit.",
            "operator": "v1-simulation",
        },
    )
    if review_response.status_code != 200:
        raise RuntimeError(f"returned_approved: review failed {review_response.text}")
    await _wait_for_transition(lead_id, "lead.return_approved")
    return {
        "scenario": "returned_approved",
        "status": "passed",
        "webhook_response": payload,
        "return_response": return_payload,
        "review_response": _json(review_response),
        "buyer_hits": _hits_for_lead(lead_id),
        "evidence": await _lead_evidence(lead_id),
    }


async def _scenario_unsold_no_buyer(
    client: httpx.AsyncClient, run_id: str, run_seed: int
) -> dict[str, Any]:
    payload = await _submit_lead(
        client,
        scenario="unsold_no_buyer",
        run_id=run_id,
        phone=_phone(run_seed, 3),
        email=f"unsold-no-buyer-{run_id}@example.com",
        state="GA",
        zip_code="30301",
        campaign_id="v1-simulation-unsold-no-buyer",
    )
    lead_id = str(payload["lead_id"])
    await _wait_for_transition(lead_id, "lead.unsold")
    return {
        "scenario": "unsold_no_buyer",
        "status": "passed",
        "webhook_response": payload,
        "buyer_hits": _hits_for_lead(lead_id),
        "evidence": await _lead_evidence(lead_id),
    }


async def _scenario_rejected_low_quality(
    client: httpx.AsyncClient, run_id: str, run_seed: int
) -> dict[str, Any]:
    payload = await _submit_lead(
        client,
        scenario="rejected_low_quality",
        run_id=run_id,
        phone=_phone(run_seed, 4),
        email=f"rejected-low-quality-{run_id}@example.com",
        state="TX",
        zip_code="78701",
        campaign_id="v1-simulation-reject-low_quality",
    )
    lead_id = str(payload["lead_id"])
    await _wait_for_transition(lead_id, "lead.rejected")
    return {
        "scenario": "rejected_low_quality",
        "status": "passed",
        "webhook_response": payload,
        "buyer_hits": _hits_for_lead(lead_id),
        "evidence": await _lead_evidence(lead_id),
    }


async def _scenario_duplicate_capture(
    client: httpx.AsyncClient, run_id: str, run_seed: int
) -> dict[str, Any]:
    scenario = "duplicate_capture"
    phone = _phone(run_seed, 5)
    page_hash = _page_hash(run_id, scenario, "duplicate")
    webhook_id = f"v1-simulation-{scenario}-{uuid4()}"
    envelope = _envelope(
        scenario=scenario,
        run_id=run_id,
        phone=phone,
        email=f"duplicate-capture-{run_id}@example.com",
        state="GA",
        zip_code="30301",
        campaign_id="v1-simulation-duplicate-capture",
        page_hash=page_hash,
    )
    first = await _post_webhook(client, envelope, webhook_id)
    second = await _post_webhook(client, envelope, webhook_id)
    if first.status_code != 200 or second.status_code != 200:
        raise RuntimeError(f"duplicate_capture: responses {first.status_code}/{second.status_code}")
    first_payload = _json(first)
    second_payload = _json(second)
    if first_payload.get("lead_id") != second_payload.get("lead_id"):
        raise RuntimeError(f"duplicate_capture: lead ids differed {first_payload}/{second_payload}")
    if second_payload.get("status") != "accepted-duplicate":
        raise RuntimeError(f"duplicate_capture: second response was {second_payload}")
    lead_id = str(first_payload["lead_id"])
    await _wait_for_transition(lead_id, "lead.captured")
    return {
        "scenario": scenario,
        "status": "passed",
        "first_response": first_payload,
        "second_response": second_payload,
        "lead_rows_for_phone_hash": await _lead_count_for(phone, page_hash),
        "audit_rows_for_webhook_id": await _audit_count_for(webhook_id),
        "evidence": await _lead_evidence(lead_id),
    }


async def _scenario_suppressed_opt_out(
    client: httpx.AsyncClient, run_id: str, run_seed: int
) -> dict[str, Any]:
    scenario = "suppressed_opt_out"
    phone = _phone(run_seed, 6)
    email = f"suppressed-opt-out-{run_id}@example.com"
    opt_out = await client.post(
        f"{FORM_RECEIVER_BASE_URL}/v1/privacy/opt-out",
        json={"phone": phone, "email": email, "reason": "v1_local_simulation_opt_out"},
    )
    if opt_out.status_code != 200:
        raise RuntimeError(f"suppressed_opt_out: opt-out failed {opt_out.text}")
    payload = await _submit_lead(
        client,
        scenario=scenario,
        run_id=run_id,
        phone=phone,
        email=email,
        state="TX",
        zip_code="78701",
        campaign_id="v1-simulation-suppressed-opt-out",
    )
    if payload.get("status") != "suppressed":
        raise RuntimeError(f"suppressed_opt_out: expected suppressed response, got {payload}")
    return {
        "scenario": scenario,
        "status": "passed",
        "opt_out_response": _json(opt_out),
        "webhook_response": payload,
        "lead_id_created": bool(payload.get("lead_id")),
    }


async def _scenario_nurtured_unsold(
    client: httpx.AsyncClient, run_id: str, run_seed: int
) -> dict[str, Any]:
    payload = await _submit_lead(
        client,
        scenario="nurtured_unsold",
        run_id=run_id,
        phone=_phone(run_seed, 7),
        email=f"nurtured-unsold-{run_id}@example.com",
        state="GA",
        zip_code="30301",
        campaign_id="v1-simulation-nurtured-unsold",
    )
    lead_id = str(payload["lead_id"])
    transition = await _wait_for_transition(lead_id, "lead.nurtured")
    if transition.payload_json.get("external_contact_made") is not False:
        raise RuntimeError(f"nurtured_unsold: contact flag missing {transition.payload_json}")
    return {
        "scenario": "nurtured_unsold",
        "status": "passed",
        "webhook_response": payload,
        "nurture_payload": transition.payload_json,
        "evidence": await _lead_evidence(lead_id),
    }


async def _scenario_nurtured_rejected(
    client: httpx.AsyncClient, run_id: str, run_seed: int
) -> dict[str, Any]:
    payload = await _submit_lead(
        client,
        scenario="nurtured_rejected",
        run_id=run_id,
        phone=_phone(run_seed, 8),
        email=f"nurtured-rejected-{run_id}@example.com",
        state="TX",
        zip_code="78701",
        campaign_id="v1-simulation-reject-nurtured",
    )
    lead_id = str(payload["lead_id"])
    transition = await _wait_for_transition(lead_id, "lead.nurtured")
    if transition.payload_json.get("external_contact_made") is not False:
        raise RuntimeError(f"nurtured_rejected: contact flag missing {transition.payload_json}")
    return {
        "scenario": "nurtured_rejected",
        "status": "passed",
        "webhook_response": payload,
        "nurture_payload": transition.payload_json,
        "evidence": await _lead_evidence(lead_id),
    }


ScenarioFn = Callable[[httpx.AsyncClient, str, int], Awaitable[dict[str, Any]]]

SCENARIOS: list[tuple[str, ScenarioFn]] = [
    ("qualified_sold", _scenario_qualified_sold),
    ("returned_approved", _scenario_returned_approved),
    ("unsold_no_buyer", _scenario_unsold_no_buyer),
    ("rejected_low_quality", _scenario_rejected_low_quality),
    ("duplicate_capture", _scenario_duplicate_capture),
    ("suppressed_opt_out", _scenario_suppressed_opt_out),
    ("nurtured_unsold", _scenario_nurtured_unsold),
    ("nurtured_rejected", _scenario_nurtured_rejected),
]


async def _service_health(client: httpx.AsyncClient) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for name, url in {
        "form_receiver": f"{FORM_RECEIVER_BASE_URL}/readyz",
        "ping_post": f"{PING_POST_URL}/readyz",
    }.items():
        response = await client.get(url)
        checks[name] = {"status_code": response.status_code, "body": _json(response)}
    return checks


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Run V1 local simulation scenarios.")
    parser.add_argument("--output-dir", default="testing/runs")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    _configure_database_url()
    await _seed()

    started_at = datetime.now(UTC)
    run_id = args.run_id or f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    run_seed = int(time.time()) % 100_000
    output_dir = Path(args.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = output_dir / "v1-simulation-evidence.json"
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "synthetic_only": True,
        "external_contact_allowed": False,
        "buyer_listener": f"http://{LISTENER_HOST}:{LISTENER_PORT}",
        "scenarios": [],
    }

    runner = await _start_buyer_listener()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            manifest["service_health"] = await _service_health(client)
            for scenario_name, scenario_fn in SCENARIOS:
                print(f"[simulate] {scenario_name} ... ", end="", flush=True)
                result = await scenario_fn(client, run_id, run_seed)
                manifest["scenarios"].append(result)
                print("OK")
            readiness = await client.get(
                f"{PING_POST_URL}/v1/admin/launch-readiness",
                params={
                    "market_zip": "78701",
                    "service": "tree_removal",
                    "campaign_budget_cents": 1000,
                },
            )
            if readiness.status_code != 200:
                raise RuntimeError(f"readiness failed {readiness.status_code}: {readiness.text}")
            manifest["readiness"] = _json(readiness)
    finally:
        await runner.cleanup()
        manifest["finished_at"] = datetime.now(UTC).isoformat()
        evidence_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    failed = [s for s in manifest["scenarios"] if s.get("status") != "passed"]
    if failed:
        print(f"[simulate] FAIL evidence={evidence_path}")
        return 1
    print(f"[simulate] PASS evidence={evidence_path}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
