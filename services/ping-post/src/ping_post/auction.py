"""parallel ping fan-out + winner selection + post.

design notes:
- every step that crosses the network has a timeout and is observable.
- bid window is hard-capped at 5s; late bids are dropped (not "wait for the slow guy").
- we sign every webhook with hmac-sha256 over `<timestamp>.<body>` to prevent replay.
- saga state lives in hatchet, not in this process. crash-resume is hatchet's job.
- we never expose lead pii in the ping payload. only zip, state, damage_tier, qual_score.
- the http-only path here is for testing. production path is via hatchet workflow.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from stormlead_core import (
    Buyer,
    DamageTier,
    Lead,
    LeadStatus,
    PingPostResult,
    evaluate_filter,
    get_logger,
)
from stormlead_db import BillingEvent, BuyerRow, LeadRow, PingAttempt, PostResult, get_session

log = get_logger(__name__)

# tunables. exposed via env in production.
PING_TIMEOUT_S = 2.5
POST_TIMEOUT_S = 5.0
BID_WINDOW_S = 5.0
MAX_PARALLEL_PINGS = 50


@dataclass
class PingResponse:
    buyer_id: UUID
    accepted: bool
    bid_cents: int | None
    response_ms: int
    status_code: int | None
    body: str | None
    error: str | None


def _ping_payload(lead: Lead) -> dict:
    """sanitized payload that goes to all pinged buyers.

    strict rule: no PII. buyers can see geography, tier, qualification score,
    damage description summary (NOT raw text — sanitized by qualify agent),
    storm context. they get full PII only after winning.
    """
    return {
        "lead_id": str(lead.id),
        "state": lead.state,
        "city": lead.city,
        "zip": lead.zip,
        "damage_tier": lead.damage_tier.value if lead.damage_tier else None,
        "qualification_score": lead.qualification_score or 0.0,
        "property_avm_band": _avm_band(lead.property_avm),
        "owner_occupied": lead.owner_occupied,
        "year_built_band": _year_band(lead.year_built),
        "storm_id": str(lead.storm_id) if lead.storm_id else None,
        "source": lead.source.value,
    }


def _avm_band(avm: Decimal | None) -> str:
    if avm is None:
        return "unknown"
    if avm < 150_000:
        return "lt_150k"
    if avm < 300_000:
        return "150k_300k"
    if avm < 500_000:
        return "300k_500k"
    if avm < 1_000_000:
        return "500k_1m"
    return "gt_1m"


def _year_band(y: int | None) -> str:
    if y is None:
        return "unknown"
    if y < 1980:
        return "pre_1980"
    if y < 2000:
        return "1980_2000"
    if y < 2015:
        return "2000_2015"
    return "post_2015"


def _sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    """standard webhooks compatible: hmac-sha256 over '<timestamp>.<body>'."""
    msg = f"{timestamp}.".encode() + body
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"v1,{sig}"


async def _ping_one(
    client: httpx.AsyncClient,
    buyer: Buyer,
    payload: dict,
) -> PingResponse:
    started = time.perf_counter()
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "Webhook-Timestamp": ts,
        "Webhook-Signature": _sign_webhook(buyer.webhook_secret, ts, body),
        "Webhook-Id": str(uuid4()),
        "X-Stormlead-Mode": "ping",
    }
    try:
        r = await client.post(
            buyer.webhook_url,
            content=body,
            headers=headers,
            timeout=PING_TIMEOUT_S,
        )
        dur_ms = int((time.perf_counter() - started) * 1000)
        # buyer responds {"accept": true, "bid_cents": 7500} or {"accept": false}
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = {}
        accepted = bool(data.get("accept"))
        bid_cents = int(data["bid_cents"]) if accepted and "bid_cents" in data else None
        return PingResponse(
            buyer_id=buyer.id,
            accepted=accepted and bid_cents is not None,
            bid_cents=bid_cents,
            response_ms=dur_ms,
            status_code=r.status_code,
            body=r.text[:1024],
            error=None,
        )
    except httpx.TimeoutException:
        return PingResponse(
            buyer_id=buyer.id,
            accepted=False,
            bid_cents=None,
            response_ms=int((time.perf_counter() - started) * 1000),
            status_code=None,
            body=None,
            error="timeout",
        )
    except Exception as e:  # noqa: BLE001
        return PingResponse(
            buyer_id=buyer.id,
            accepted=False,
            bid_cents=None,
            response_ms=int((time.perf_counter() - started) * 1000),
            status_code=None,
            body=None,
            error=f"{type(e).__name__}: {e}",
        )


async def _select_eligible_buyers(lead: Lead) -> list[Buyer]:
    """pull buyers from db, filter by status + cel expression."""
    async with get_session() as s:
        rows = (
            await s.execute(
                select(BuyerRow).where(
                    BuyerRow.status == "active",
                    BuyerRow.deposit_balance > Decimal("0"),
                )
            )
        ).scalars().all()

    eligible = []
    for r in rows:
        buyer = Buyer(
            id=r.id,
            name=r.name,
            company=r.company,
            contact_email=r.contact_email,
            contact_phone_e164=r.contact_phone_e164,
            status=r.status,
            license_number=r.license_number,
            license_state=r.license_state,
            license_verified_at=r.license_verified_at,
            webhook_url=r.webhook_url,
            webhook_secret=r.webhook_secret,
            bid_per_lead_t1_t2=r.bid_per_lead_t1_t2,
            bid_per_lead_t3=r.bid_per_lead_t3,
            bid_per_call=r.bid_per_call,
            filter_expression=r.filter_expression,
            daily_cap=r.daily_cap,
            monthly_budget=r.monthly_budget,
            deposit_balance=r.deposit_balance,
            lifetime_spend=r.lifetime_spend,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        verdict = evaluate_filter(buyer.filter_expression, lead)
        if verdict.matches:
            eligible.append(buyer)
    log.info("buyers.eligible", lead_id=str(lead.id), count=len(eligible))
    return eligible


async def _record_pings(
    lead_id: UUID,
    payload: dict,
    responses: list[PingResponse],
) -> None:
    async with get_session() as s:
        for r in responses:
            s.add(
                PingAttempt(
                    lead_id=lead_id,
                    buyer_id=r.buyer_id,
                    ping_payload=payload,
                    accepted=r.accepted,
                    bid_cents=r.bid_cents,
                    response_ms=r.response_ms,
                    response_status_code=r.status_code,
                    response_body=r.body,
                    error=r.error,
                )
            )


def _pick_winner(
    responses: list[PingResponse],
    buyers_by_id: dict[UUID, Buyer],
    damage_tier: DamageTier | None,
) -> tuple[PingResponse, Buyer] | None:
    accepting = [
        r
        for r in responses
        if r.accepted
        and r.bid_cents
        and _buyer_can_afford_bid(buyers_by_id[r.buyer_id], r.bid_cents)
    ]
    if not accepting:
        return None
    # highest bid wins. ties broken by lowest response time (fastest buyer).
    accepting.sort(key=lambda r: (-(r.bid_cents or 0), r.response_ms))
    winner = accepting[0]
    return winner, buyers_by_id[winner.buyer_id]


def _buyer_can_afford_bid(buyer: Buyer, bid_cents: int) -> bool:
    return buyer.deposit_balance >= Decimal(bid_cents) / Decimal(100)


def _debit_amount(bid_cents: int) -> Decimal:
    return Decimal(bid_cents) / Decimal(100)


async def _post_to_winner(
    client: httpx.AsyncClient,
    buyer: Buyer,
    lead: Lead,
    bid_cents: int,
) -> tuple[bool, int | None, str | None]:
    """deliver full lead with PII to winning buyer. signed."""
    body = json.dumps(
        {
            "lead_id": str(lead.id),
            "name": lead.name,
            "phone": lead.phone_e164,
            "email": lead.email,
            "address": {
                "line1": lead.address_line1,
                "city": lead.city,
                "state": lead.state,
                "zip": lead.zip,
            },
            "damage_tier": lead.damage_tier.value if lead.damage_tier else None,
            "damage_description": lead.damage_description,
            "photo_urls": [],  # presigned in production
            "consent": {
                "text": lead.consent_text,
                "ip": lead.consent_ip,
                "ts": lead.consent_at.isoformat(),
                "trustedform_url": lead.trustedform_cert_url,
            },
            "purchase": {
                "bid_cents": bid_cents,
                "currency": "USD",
                "exclusive": True,
            },
        }
    ).encode()
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "Webhook-Timestamp": ts,
        "Webhook-Signature": _sign_webhook(buyer.webhook_secret, ts, body),
        "Webhook-Id": str(uuid4()),
        "X-Stormlead-Mode": "post",
    }
    try:
        r = await client.post(buyer.webhook_url, content=body, headers=headers, timeout=POST_TIMEOUT_S)
        return (200 <= r.status_code < 300, r.status_code, r.text[:2048])
    except Exception as e:  # noqa: BLE001
        return (False, None, f"{type(e).__name__}: {e}")


async def run_auction(lead: Lead) -> PingPostResult:
    """run a full ping-post cycle for one lead. returns the result."""
    started = time.perf_counter()
    buyers = await _select_eligible_buyers(lead)
    if not buyers:
        return PingPostResult(
            event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            lead_id=lead.id,
            pinged_buyer_ids=[],
            winning_buyer_id=None,
            winning_bid_cents=None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            damage_tier=lead.damage_tier,
        )

    payload = _ping_payload(lead)
    buyers_by_id = {b.id: b for b in buyers}

    sem = asyncio.Semaphore(MAX_PARALLEL_PINGS)

    async with httpx.AsyncClient(http2=True) as client:

        async def bounded(b: Buyer) -> PingResponse:
            async with sem:
                return await _ping_one(client, b, payload)

        # bid window: cancel anything still pending after BID_WINDOW_S
        try:
            responses = await asyncio.wait_for(
                asyncio.gather(*(bounded(b) for b in buyers), return_exceptions=False),
                timeout=BID_WINDOW_S,
            )
        except asyncio.TimeoutError:
            log.warning("ping.bid_window_timeout", lead_id=str(lead.id))
            responses = []

        await _record_pings(lead.id, payload, responses)

        winner_pair = _pick_winner(responses, buyers_by_id, lead.damage_tier)
        winning_buyer_id: UUID | None = None
        winning_bid: int | None = None

        if winner_pair:
            ping_resp, buyer = winner_pair
            winning_buyer_id = buyer.id
            winning_bid = ping_resp.bid_cents
            ok, status, body = await _post_to_winner(client, buyer, lead, ping_resp.bid_cents or 0)

            async with get_session() as s:
                s.add(
                    PostResult(
                        lead_id=lead.id,
                        buyer_id=buyer.id,
                        bid_cents=ping_resp.bid_cents or 0,
                        delivered=ok,
                        response_status_code=status,
                        response_body=body,
                    )
                )
                # update lead status
                lead_row = await s.get(LeadRow, lead.id)
                if lead_row:
                    lead_row.status = LeadStatus.SOLD.value if ok else LeadStatus.UNSOLD.value
                buyer_row = await s.get(BuyerRow, buyer.id)
                if ok and buyer_row:
                    debit = _debit_amount(ping_resp.bid_cents or 0)
                    buyer_row.deposit_balance -= debit
                    buyer_row.lifetime_spend += debit
                    s.add(
                        BillingEvent(
                            buyer_id=buyer.id,
                            lead_id=lead.id,
                            event_type="lead.posted",
                            amount_cents=-(ping_resp.bid_cents or 0),
                            metadata_json={
                                "post_result_status_code": status,
                                "exclusive": True,
                            },
                        )
                    )
        else:
            async with get_session() as s:
                lead_row = await s.get(LeadRow, lead.id)
                if lead_row:
                    lead_row.status = LeadStatus.UNSOLD.value

        return PingPostResult(
            event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            lead_id=lead.id,
            pinged_buyer_ids=[b.id for b in buyers],
            winning_buyer_id=winning_buyer_id,
            winning_bid_cents=winning_bid,
            duration_ms=int((time.perf_counter() - started) * 1000),
            damage_tier=lead.damage_tier,
        )
