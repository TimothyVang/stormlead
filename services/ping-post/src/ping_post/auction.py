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
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from hatchet_sdk import Hatchet
from sqlalchemy import func, select, update
from stormlead_core import (
    Buyer,
    BuyerSalesStage,
    BuyerStatus,
    DamageTier,
    Lead,
    LeadStatus,
    PingPostResult,
    PipelineState,
    bind_correlation_id,
    emit_event,
    emit_metric,
    evaluate_filter,
    get_logger,
)
from stormlead_db import (
    BillingEvent,
    BuyerRow,
    LeadRow,
    PingAttempt,
    PostResult,
    get_session,
    record_transition,
)

log = get_logger(__name__)
_hatchet_client: Hatchet | None = None


def _hatchet() -> Hatchet:
    global _hatchet_client
    if _hatchet_client is None:
        _hatchet_client = Hatchet(debug=False)
    return _hatchet_client


# tunables. exposed via env in production.
PING_TIMEOUT_S = 2.5
POST_TIMEOUT_S = 5.0
BID_WINDOW_S = 5.0
MAX_PARALLEL_PINGS = 50
POST_MAX_ATTEMPTS = 3
POST_RETRY_BASE_DELAY_S = 0.25


@dataclass
class PingResponse:
    buyer_id: UUID
    accepted: bool
    bid_cents: int | None
    response_ms: int
    status_code: int | None
    body: str | None
    error: str | None


def _routing_thresholds() -> tuple[float, float]:
    return (
        float(os.getenv("LEAD_ROUTE_AB_MIN_SCORE", "0.8")),
        float(os.getenv("LEAD_HOLD_MIN_SCORE", "0.6")),
    )


def _lead_can_enter_auction(lead: Lead) -> tuple[bool, str]:
    if lead.blocked_for_fraud:
        return False, "blocked_for_fraud"
    if lead.hold_for_review:
        return False, "held_for_review"
    score = lead.score if lead.score is not None else (lead.qualification_score or 0.0)
    ab_min, hold_min = _routing_thresholds()
    if score >= ab_min:
        return True, "route_ab"
    if score < hold_min:
        return False, "score_below_hold_threshold"
    lead_class = lead.lead_class.value if lead.lead_class else None
    if lead_class in {"c", "d"}:
        return False, "class_requires_review"
    return True, "route_b"


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


def _delivery_idempotency_key(lead_id: UUID, buyer_id: UUID, bid_cents: int) -> str:
    raw = f"{lead_id}:{buyer_id}:{bid_cents}".encode()
    return hashlib.sha256(raw).hexdigest()


def _should_retry_post(status_code: int | None, error: Exception | None) -> bool:
    if error is not None:
        return isinstance(error, (httpx.TimeoutException, httpx.NetworkError))
    if status_code is None:
        return False
    return status_code == 429 or 500 <= status_code <= 599


async def _ping_one(
    client: httpx.AsyncClient,
    buyer: Buyer,
    payload: dict,
) -> PingResponse:
    bind_correlation_id(payload.get("lead_id"))
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
        except Exception:
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
    except Exception as e:
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
            (
                await s.execute(
                    select(BuyerRow).where(
                        BuyerRow.status == "active",
                        BuyerRow.deposit_balance > Decimal("0"),
                    )
                )
            )
            .scalars()
            .all()
        )

    eligible = []
    for r in rows:
        buyer = Buyer(
            id=r.id,
            name=r.name,
            company=r.company,
            contact_email=r.contact_email,
            contact_phone_e164=r.contact_phone_e164,
            status=BuyerStatus(r.status),
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
            sales_stage=BuyerSalesStage(r.sales_stage),
            notes=r.notes,
            next_follow_up_at=r.next_follow_up_at,
            services=r.services or [],
            target_zips=r.target_zips or [],
            exclusive_zips=r.exclusive_zips or [],
            low_balance_threshold=r.low_balance_threshold,
            deposit_balance=r.deposit_balance,
            lifetime_spend=r.lifetime_spend,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        verdict = evaluate_filter(buyer.filter_expression, lead)
        if (
            verdict.matches
            and _buyer_matches_paid_pilot_rules(buyer, lead)
            and await _buyer_within_caps(buyer)
        ):
            eligible.append(buyer)
    log.info("buyers.eligible", lead_id=str(lead.id), count=len(eligible))
    return eligible


def _buyer_matches_paid_pilot_rules(buyer: Buyer, lead: Lead) -> bool:
    """Business eligibility that should not live inside freeform CEL."""
    lead_class = lead.lead_class.value if lead.lead_class else None
    if lead_class in {"c", "d"}:
        return False
    if buyer.target_zips and lead.zip not in buyer.target_zips:
        return False
    if lead.requested_service and buyer.services and lead.requested_service not in buyer.services:
        return False
    return True


async def _buyer_within_caps(buyer: Buyer) -> bool:
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with get_session() as s:
        day_count = await s.scalar(
            select(func.count(PostResult.id)).where(
                PostResult.buyer_id == buyer.id,
                PostResult.delivered.is_(True),
                PostResult.created_at >= day_start,
            )
        )
        month_spend = await s.scalar(
            select(func.coalesce(func.sum(PostResult.bid_cents), 0)).where(
                PostResult.buyer_id == buyer.id,
                PostResult.delivered.is_(True),
                PostResult.created_at >= month_start,
            )
        )
    if (day_count or 0) >= buyer.daily_cap:
        return False
    return Decimal(int(month_spend or 0)) / Decimal(100) < buyer.monthly_budget


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


async def _record_pipeline_transition(
    lead_id: UUID,
    from_state: PipelineState,
    to_state: PipelineState,
    event_type: str,
    payload: dict,
) -> None:
    async with get_session() as s:
        await record_transition(
            s,
            lead_id=lead_id,
            from_state=from_state,
            to_state=to_state,
            event_type=event_type,
            task_name="ping_post.run_auction",
            payload=payload,
        )


def _push_lead_event(event_name: str, lead_id: UUID, payload: dict | None = None) -> None:
    _hatchet().event.push(
        event_name,
        {"lead_id": str(lead_id), "source_event": event_name, **(payload or {})},
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


async def _reserve_buyer_wallet(
    buyer_id: UUID,
    lead_id: UUID,
    bid_cents: int,
) -> bool:
    debit = _debit_amount(bid_cents)
    async with get_session() as s:
        result = await s.execute(
            update(BuyerRow)
            .where(
                BuyerRow.id == buyer_id,
                BuyerRow.status == "active",
                BuyerRow.deposit_balance >= debit,
            )
            .values(
                deposit_balance=BuyerRow.deposit_balance - debit,
                lifetime_spend=BuyerRow.lifetime_spend + debit,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            log.warning(
                "buyer.wallet_reserve_rejected",
                buyer_id=str(buyer_id),
                lead_id=str(lead_id),
                bid_cents=bid_cents,
            )
            return False
        s.add(
            BillingEvent(
                buyer_id=buyer_id,
                lead_id=lead_id,
                event_type="lead.reserved",
                amount_cents=-bid_cents,
                metadata_json={"exclusive": True},
            )
        )
        return True


async def _credit_failed_delivery(
    buyer_id: UUID,
    lead_id: UUID,
    bid_cents: int,
    status: int | None,
) -> None:
    credit = _debit_amount(bid_cents)
    async with get_session() as s:
        await s.execute(
            update(BuyerRow)
            .where(BuyerRow.id == buyer_id)
            .values(
                deposit_balance=BuyerRow.deposit_balance + credit,
                lifetime_spend=BuyerRow.lifetime_spend - credit,
            )
        )
        s.add(
            BillingEvent(
                buyer_id=buyer_id,
                lead_id=lead_id,
                event_type="lead.delivery_failed_credit",
                amount_cents=bid_cents,
                metadata_json={"post_result_status_code": status},
            )
        )


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
    idempotency_key = _delivery_idempotency_key(lead.id, buyer.id, bid_cents)
    headers = {
        "Content-Type": "application/json",
        "Webhook-Timestamp": ts,
        "Webhook-Signature": _sign_webhook(buyer.webhook_secret, ts, body),
        "Webhook-Id": str(uuid4()),
        "Idempotency-Key": idempotency_key,
        "X-Stormlead-Mode": "post",
    }
    for attempt in range(1, POST_MAX_ATTEMPTS + 1):
        try:
            r = await client.post(
                buyer.webhook_url, content=body, headers=headers, timeout=POST_TIMEOUT_S
            )
            ok = 200 <= r.status_code < 300
            if ok:
                emit_event(
                    "sold", lead_id=str(lead.id), service="ping-post", buyer_id=str(buyer.id)
                )
                emit_metric("funnel.sold", lead_id=str(lead.id), service="ping-post")
                log.info(
                    "delivery.post_succeeded",
                    lead_id=str(lead.id),
                    buyer_id=str(buyer.id),
                    bid_cents=bid_cents,
                    attempt=attempt,
                )
                return (True, r.status_code, r.text[:2048])
            retry = _should_retry_post(r.status_code, None)
            log.warning(
                "delivery.post_failed",
                lead_id=str(lead.id),
                buyer_id=str(buyer.id),
                bid_cents=bid_cents,
                attempt=attempt,
                status_code=r.status_code,
                will_retry=retry and attempt < POST_MAX_ATTEMPTS,
            )
            if retry and attempt < POST_MAX_ATTEMPTS:
                emit_event(
                    "retried",
                    lead_id=str(lead.id),
                    service="ping-post",
                    buyer_id=str(buyer.id),
                    attempt=attempt,
                )
                emit_metric("funnel.retried", lead_id=str(lead.id), service="ping-post")
                await asyncio.sleep(POST_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))
                continue
            return (False, r.status_code, r.text[:2048])
        except Exception as e:
            retry = _should_retry_post(None, e)
            log.warning(
                "delivery.post_exception",
                lead_id=str(lead.id),
                buyer_id=str(buyer.id),
                bid_cents=bid_cents,
                attempt=attempt,
                error=f"{type(e).__name__}: {e}",
                will_retry=retry and attempt < POST_MAX_ATTEMPTS,
            )
            if retry and attempt < POST_MAX_ATTEMPTS:
                emit_event(
                    "retried",
                    lead_id=str(lead.id),
                    service="ping-post",
                    buyer_id=str(buyer.id),
                    attempt=attempt,
                )
                emit_metric("funnel.retried", lead_id=str(lead.id), service="ping-post")
                await asyncio.sleep(POST_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))
                continue
            return (False, None, f"{type(e).__name__}: {e}")
    return (False, None, "retry_exhausted")


async def run_auction(lead: Lead) -> PingPostResult:
    """run a full ping-post cycle for one lead. returns the result."""
    bind_correlation_id(str(lead.id))
    started = time.perf_counter()
    allowed, reason = _lead_can_enter_auction(lead)
    if not allowed:
        log.info("lead.not_eligible_for_auction", lead_id=str(lead.id), reason=reason)
        return PingPostResult(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            lead_id=lead.id,
            pinged_buyer_ids=[],
            winning_buyer_id=None,
            winning_bid_cents=None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            damage_tier=lead.damage_tier,
        )

    buyers = await _select_eligible_buyers(lead)
    await _record_pipeline_transition(
        lead.id,
        PipelineState.QUALIFIED,
        PipelineState.AUCTIONED,
        "lead.auctioned",
        {"eligible_buyers": len(buyers)},
    )
    if not buyers:
        await _record_pipeline_transition(
            lead.id,
            PipelineState.AUCTIONED,
            PipelineState.UNSOLD,
            "lead.unsold",
            {"reason": "no_eligible_buyers"},
        )
        emit_event("auctioned", lead_id=str(lead.id), service="ping-post", buyers=0)
        emit_metric("funnel.auctioned", lead_id=str(lead.id), service="ping-post", buyers=0)
        emit_event("unsold", lead_id=str(lead.id), service="ping-post")
        emit_metric("funnel.unsold", lead_id=str(lead.id), service="ping-post")
        emit_metric(
            "auction.win_rate",
            value=0,
            lead_id=str(lead.id),
            service="ping-post",
            eligible_buyers=0,
        )
        _push_lead_event("lead.unsold", lead.id, {"reason": "no_eligible_buyers"})
        return PingPostResult(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
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
        except TimeoutError:
            log.warning("ping.bid_window_timeout", lead_id=str(lead.id))
            responses = []

        await _record_pings(lead.id, payload, responses)

        winner_pair = _pick_winner(responses, buyers_by_id, lead.damage_tier)
        winning_buyer_id: UUID | None = None
        winning_bid: int | None = None

        if winner_pair:
            ping_resp, buyer = winner_pair
            bid_cents = ping_resp.bid_cents or 0
            reserved = await _reserve_buyer_wallet(buyer.id, lead.id, bid_cents)
            if reserved:
                winning_buyer_id = buyer.id
                winning_bid = bid_cents
                ok, status, body = await _post_to_winner(client, buyer, lead, bid_cents)
            else:
                ok, status, body = False, None, "buyer wallet/status changed before post"

            async with get_session() as s:
                s.add(
                    PostResult(
                        lead_id=lead.id,
                        buyer_id=buyer.id,
                        bid_cents=bid_cents,
                        delivered=ok,
                        response_status_code=status,
                        response_body=body,
                    )
                )
                # update lead status
                lead_row = await s.get(LeadRow, lead.id)
                if lead_row:
                    lead_row.status = LeadStatus.SOLD.value if ok else LeadStatus.UNSOLD.value
                await record_transition(
                    s,
                    lead_id=lead.id,
                    from_state=PipelineState.AUCTIONED,
                    to_state=PipelineState.SOLD if ok else PipelineState.UNSOLD,
                    event_type="lead.sold" if ok else "lead.unsold",
                    task_name="ping_post.run_auction",
                    payload={
                        "buyer_id": str(buyer.id),
                        "bid_cents": bid_cents,
                        "post_status_code": status,
                    },
                )
                if ok:
                    emit_metric(
                        "auction.win_rate",
                        value=1,
                        lead_id=str(lead.id),
                        service="ping-post",
                        eligible_buyers=len(buyers),
                    )
                    s.add(
                        BillingEvent(
                            buyer_id=buyer.id,
                            lead_id=lead.id,
                            event_type="lead.posted",
                            amount_cents=0,
                            metadata_json={
                                "reserved_cents": bid_cents,
                                "post_result_status_code": status,
                                "exclusive": True,
                            },
                        )
                    )
                else:
                    emit_metric(
                        "auction.win_rate",
                        value=0,
                        lead_id=str(lead.id),
                        service="ping-post",
                        eligible_buyers=len(buyers),
                    )
                    _push_lead_event(
                        "lead.unsold",
                        lead.id,
                        {"reason": "post_failed", "buyer_id": str(buyer.id)},
                    )
            if reserved and not ok:
                emit_event(
                    "refunded", lead_id=str(lead.id), service="ping-post", buyer_id=str(buyer.id)
                )
                emit_metric("funnel.refunded", lead_id=str(lead.id), service="ping-post")
                await _credit_failed_delivery(buyer.id, lead.id, bid_cents, status)
        else:
            await _record_pipeline_transition(
                lead.id,
                PipelineState.AUCTIONED,
                PipelineState.UNSOLD,
                "lead.unsold",
                {"reason": "no_accepted_bid", "eligible_buyers": len(buyers)},
            )
            emit_event("auctioned", lead_id=str(lead.id), service="ping-post", buyers=len(buyers))
            emit_metric(
                "funnel.auctioned", lead_id=str(lead.id), service="ping-post", buyers=len(buyers)
            )
            emit_event("unsold", lead_id=str(lead.id), service="ping-post")
            emit_metric("funnel.unsold", lead_id=str(lead.id), service="ping-post")
            emit_metric(
                "auction.win_rate",
                value=0,
                lead_id=str(lead.id),
                service="ping-post",
                eligible_buyers=len(buyers),
            )
            _push_lead_event("lead.unsold", lead.id, {"reason": "no_accepted_bid"})
            async with get_session() as s:
                lead_row = await s.get(LeadRow, lead.id)
                if lead_row:
                    lead_row.status = LeadStatus.UNSOLD.value

        return PingPostResult(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            lead_id=lead.id,
            pinged_buyer_ids=[b.id for b in buyers],
            winning_buyer_id=winning_buyer_id,
            winning_bid_cents=winning_bid,
            duration_ms=int((time.perf_counter() - started) * 1000),
            damage_tier=lead.damage_tier,
        )
