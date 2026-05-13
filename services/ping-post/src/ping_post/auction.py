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
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from hatchet_sdk import Hatchet
from sqlalchemy import func, select, text, update
from stormlead_core import (
    Buyer,
    BuyerSalesStage,
    BuyerStatus,
    DamageTier,
    Lead,
    LeadStatus,
    PingPostResult,
    PipelineState,
    ProviderArea,
    bind_correlation_id,
    emit_event,
    emit_metric,
    evaluate_filter,
    get_logger,
    provider_decision,
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

from ping_post.buyer_activation import (
    buyer_activation_readiness,
    buyer_coverage_zips,
    buyer_exclusive_zips,
)

log = get_logger(__name__)
_hatchet_client: Hatchet | None = None


class ExclusiveZipOwnerNotReadyError(RuntimeError):
    """Raised when an active exclusive ZIP owner exists but cannot receive this lead."""


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
HIGH_RISK_SAFETY_FLAGS = frozenset(
    {"power_line", "injury", "active_danger", "roof_impact", "structure_impact"}
)
RESTRICTED_RESALE_SOURCES = frozenset(
    {"google_lsa", "local_services_ads", "google_local_services_ads"}
)
PING_SAFE_SAFETY_FLAGS = HIGH_RISK_SAFETY_FLAGS | frozenset({"emergency"})
PING_SAFE_DAMAGE_TYPES = frozenset(
    {
        "fallen_tree",
        "roof_impact",
        "tree_on_structure",
        "structure_impact",
        "broken_branch",
        "branch_removal",
        "stump",
    }
)
PING_SAFE_URGENCIES = frozenset({"emergency", "same_day", "next_day", "flexible"})
PING_SAFE_RISK_LEVELS = frozenset({"low", "medium", "high"})
PING_SAFE_JOB_SIZES = frozenset({"small", "medium", "large", "emergency"})


def _buyer_delivery_allowed(webhook_url: str) -> bool:
    return provider_decision(
        ProviderArea.BUYER_DELIVERY,
        action="buyer webhook delivery",
        target_url=webhook_url,
    ).allowed


def validate_buyer_webhook_url(value: str | None) -> str | None:
    if value is None or _buyer_delivery_allowed(value):
        return value
    raise ValueError(
        "buyer webhook_url must stay local before commercial launch approval "
        "or use an approved HTTPS buyer host after approval"
    )


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


def _valid_bid_cents(value: int | None) -> bool:
    return value is not None and value > 0


def _configured_min_bid_cents(buyer: Buyer, damage_tier: DamageTier | None) -> int:
    price = (
        buyer.bid_per_lead_t3
        if damage_tier == DamageTier.TIER_3_ON_STRUCTURE
        else buyer.bid_per_lead_t1_t2
    )
    return int(price * Decimal(100))


def _valid_bid_for_buyer(
    buyer: Buyer, bid_cents: int | None, damage_tier: DamageTier | None
) -> bool:
    if bid_cents is None or bid_cents <= 0:
        return False
    return bid_cents >= _configured_min_bid_cents(buyer, damage_tier)


def _lead_can_enter_auction(lead: Lead) -> tuple[bool, str]:
    if lead.blocked_for_fraud:
        return False, "blocked_for_fraud"
    if _lead_requires_safety_review(lead):
        return False, "safety_review_required"
    if not _lead_source_allows_resale(lead):
        return False, "restricted_source_no_resale"
    if lead.hold_for_review:
        return False, "held_for_review"
    lead_class = lead.lead_class.value if lead.lead_class else None
    if lead_class in {"c", "d"}:
        return False, "class_requires_review"
    score = lead.score if lead.score is not None else (lead.qualification_score or 0.0)
    ab_min, hold_min = _routing_thresholds()
    if score >= ab_min:
        return True, "route_ab"
    if score < hold_min:
        return False, "score_below_hold_threshold"
    return True, "route_b"


def _lead_requires_safety_review(lead: Lead) -> bool:
    if lead.damage_tier == DamageTier.TIER_4_LIFE_SAFETY:
        return True
    normalized_flags = {flag.strip().lower() for flag in lead.safety_flags if flag.strip()}
    return bool(normalized_flags & HIGH_RISK_SAFETY_FLAGS)


def _lead_source_allows_resale(lead: Lead) -> bool:
    source = getattr(lead.source, "value", lead.source)
    markers = {str(source or "").lower(), str(lead.campaign_source or "").lower()}
    return not bool(markers & RESTRICTED_RESALE_SOURCES)


def _safe_label(value: str | None, allowed: frozenset[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        return fallback
    return normalized.replace("_", " ")


def _safe_ping_safety_flags(values: list[str]) -> list[str]:
    return sorted(
        {flag.strip().lower() for flag in values if flag.strip().lower() in PING_SAFE_SAFETY_FLAGS}
    )


def _ping_damage_summary(lead: Lead) -> str:
    damage_type = _safe_label(lead.damage_type, PING_SAFE_DAMAGE_TYPES, "tree damage")
    urgency = _safe_label(lead.urgency, PING_SAFE_URGENCIES, "not specified")
    risk = _safe_label(lead.visible_risk_level, PING_SAFE_RISK_LEVELS, "unknown")
    job_size = _safe_label(lead.estimated_job_size, PING_SAFE_JOB_SIZES, "unknown")
    return (
        f"{damage_type.capitalize()} reported; urgency {urgency}; "
        f"visible risk {risk}; estimated job {job_size}."
    )


def _ping_buyer_notes(lead: Lead, safety_flags: list[str]) -> str:
    risk = str(lead.visible_risk_level or "").strip().lower()
    job_size = str(lead.estimated_job_size or "").strip().lower()
    if risk == "high" or bool(set(safety_flags) & HIGH_RISK_SAFETY_FLAGS):
        return "Pre-sale ping only; route through operator review before dispatch."
    if job_size in {"large", "emergency"}:
        return "Pre-sale ping only; confirm access, crew size, and equipment after purchase."
    return "Pre-sale ping only; confirm scope and access after purchase."


def _ping_payload(lead: Lead) -> dict:
    """sanitized payload that goes to all pinged buyers.

    strict rule: no PII. buyers can see geography, tier, qualification score,
    controlled damage summary (NOT raw homeowner or model-generated text),
    storm context. they get full PII only after winning.
    """
    safety_flags = _safe_ping_safety_flags(lead.safety_flags)
    return {
        "lead_id": str(lead.id),
        "state": lead.state,
        "city": lead.city,
        "zip": lead.zip,
        "damage_tier": lead.damage_tier.value if lead.damage_tier else None,
        "damage_type": lead.damage_type,
        "urgency": lead.urgency,
        "damage_summary": _ping_damage_summary(lead),
        "visible_risk_level": lead.visible_risk_level,
        "estimated_job_size": lead.estimated_job_size,
        "buyer_notes": _ping_buyer_notes(lead, safety_flags),
        "safety_flags": safety_flags,
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


def _auction_lock_key(lead_id: UUID) -> int:
    digest = hashlib.sha256(lead_id.bytes).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@asynccontextmanager
async def _lead_auction_lock(lead_id: UUID) -> AsyncIterator[None]:
    lock_key = _auction_lock_key(lead_id)
    async with get_session() as s:
        await s.execute(text("SELECT pg_advisory_lock(:lock_key)"), {"lock_key": lock_key})
        try:
            yield
        finally:
            await s.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": lock_key})


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
    if not _buyer_delivery_allowed(buyer.webhook_url):
        return PingResponse(
            buyer_id=buyer.id,
            accepted=False,
            bid_cents=None,
            response_ms=0,
            status_code=None,
            body=None,
            error="commercial_launch_not_approved",
        )
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
        try:
            bid_cents = int(data["bid_cents"]) if accepted and "bid_cents" in data else None
        except (TypeError, ValueError):
            bid_cents = None
        return PingResponse(
            buyer_id=buyer.id,
            accepted=accepted and _valid_bid_cents(bid_cents),
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
            (await s.execute(select(BuyerRow).where(BuyerRow.status == "active"))).scalars().all()
        )

    eligible = []
    active_exclusive_owner_exists = any(lead.zip in buyer_exclusive_zips(r) for r in rows)
    for r in rows:
        if not buyer_activation_readiness(r)["autopilot_ready"]:
            continue
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
            and _buyer_delivery_allowed(buyer.webhook_url)
            and await _buyer_within_caps(buyer)
        ):
            eligible.append(buyer)
    eligible = _apply_exclusive_zip_routing(
        lead, eligible, active_exclusive_owner_exists=active_exclusive_owner_exists
    )
    if active_exclusive_owner_exists and not eligible:
        raise ExclusiveZipOwnerNotReadyError("exclusive_buyer_not_ready")
    log.info("buyers.eligible", lead_id=str(lead.id), count=len(eligible))
    return eligible


def _apply_exclusive_zip_routing(
    lead: Lead, buyers: list[Buyer], *, active_exclusive_owner_exists: bool
) -> list[Buyer]:
    if not active_exclusive_owner_exists:
        return buyers
    lead_zip = str(lead.zip or "").strip().lower()
    return [buyer for buyer in buyers if lead_zip in buyer_exclusive_zips(buyer)]


def _buyer_matches_paid_pilot_rules(buyer: Buyer, lead: Lead) -> bool:
    """Business eligibility that should not live inside freeform CEL."""
    lead_class = lead.lead_class.value if lead.lead_class else None
    if lead_class in {"c", "d"}:
        return False
    coverage_zips = set(buyer_coverage_zips(buyer))
    if coverage_zips and lead.zip not in coverage_zips:
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
            select(func.count(BillingEvent.id)).where(
                BillingEvent.buyer_id == buyer.id,
                BillingEvent.event_type == "lead.posted",
                BillingEvent.created_at >= day_start,
            )
        )
        month_spend = await s.scalar(
            select(func.coalesce(func.sum(BillingEvent.amount_cents), 0)).where(
                BillingEvent.buyer_id == buyer.id,
                BillingEvent.event_type == "lead.posted",
                BillingEvent.created_at >= month_start,
            )
        )
    if (day_count or 0) >= buyer.daily_cap:
        return False
    return Decimal(int(month_spend or 0)) / Decimal(100) < buyer.monthly_budget


async def _persist_unauctionable_lead(lead: Lead, reason: str) -> None:
    lead_class = lead.lead_class.value if lead.lead_class else None
    async with get_session() as s:
        row = await s.get(LeadRow, lead.id)
        if row is None:
            return
        if reason == "blocked_for_fraud" or lead_class == "d":
            row.status = LeadStatus.REJECTED.value
            row.rejection_reason = reason if lead_class != "d" else "lead_class_d"
            await record_transition(
                s,
                lead_id=lead.id,
                from_state=None,
                to_state=PipelineState.REJECTED,
                event_type="lead.rejected",
                task_name="ping_post.run_auction",
                payload={"reason": row.rejection_reason, "lead_class": lead_class},
            )
            _push_lead_event("lead.rejected", lead.id, {"reason": row.rejection_reason})
            return

        if reason in {
            "class_requires_review",
            "score_below_hold_threshold",
            "held_for_review",
            "safety_review_required",
            "exclusive_buyer_not_ready",
        }:
            row.hold_for_review = True
            event_type = (
                "lead.safety_escalated"
                if reason == "safety_review_required"
                else "lead.held_for_review"
            )
            await record_transition(
                s,
                lead_id=lead.id,
                from_state=None,
                to_state=PipelineState.QUALIFIED,
                event_type=event_type,
                task_name="ping_post.run_auction",
                status="pending_review",
                payload={
                    "reason": reason,
                    "lead_class": lead_class,
                    "safety_flags": lead.safety_flags,
                },
            )
            return

        if reason == "restricted_source_no_resale":
            row.status = LeadStatus.REJECTED.value
            row.rejection_reason = reason
            await record_transition(
                s,
                lead_id=lead.id,
                from_state=None,
                to_state=PipelineState.REJECTED,
                event_type="lead.rejected",
                task_name="ping_post.run_auction",
                payload={"reason": reason, "campaign_source": lead.campaign_source},
            )
            _push_lead_event("lead.rejected", lead.id, {"reason": reason})


async def _sold_delivery_for_lead(lead_id: UUID) -> PostResult | None:
    async with get_session() as s:
        return (
            (
                await s.execute(
                    select(PostResult)
                    .where(PostResult.lead_id == lead_id, PostResult.delivered.is_(True))
                    .order_by(PostResult.created_at.desc())
                )
            )
            .scalars()
            .first()
        )


async def _delivery_result_by_key(delivery_idempotency_key: str) -> PostResult | None:
    async with get_session() as s:
        return (
            (
                await s.execute(
                    select(PostResult).where(
                        PostResult.delivery_idempotency_key == delivery_idempotency_key
                    )
                )
            )
            .scalars()
            .first()
        )


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


async def _collect_bid_window_responses(
    *,
    lead_id: UUID,
    buyers: list[Buyer],
    ping_buyer: Callable[[Buyer], Awaitable[PingResponse]],
    bid_window_s: float = BID_WINDOW_S,
) -> list[PingResponse]:
    tasks = {asyncio.ensure_future(ping_buyer(buyer)): buyer for buyer in buyers}
    done, pending = await asyncio.wait(
        tasks.keys(), timeout=bid_window_s, return_when=asyncio.ALL_COMPLETED
    )

    responses: list[PingResponse] = []
    for task in done:
        buyer = tasks[task]
        try:
            responses.append(task.result())
        except Exception as exc:
            responses.append(
                PingResponse(
                    buyer_id=buyer.id,
                    accepted=False,
                    bid_cents=None,
                    response_ms=int(bid_window_s * 1000),
                    status_code=None,
                    body=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    if pending:
        log.warning(
            "ping.partial_bid_window",
            lead_id=str(lead_id),
            completed_count=len(done),
            pending_count=len(pending),
        )
        for task in pending:
            task.cancel()
        cancelled_results = await asyncio.gather(*pending, return_exceptions=True)
        for task, result in zip(pending, cancelled_results, strict=True):
            if isinstance(result, PingResponse):
                responses.append(result)
                continue
            buyer = tasks[task]
            error = (
                "timeout" if isinstance(result, asyncio.CancelledError) else type(result).__name__
            )
            responses.append(
                PingResponse(
                    buyer_id=buyer.id,
                    accepted=False,
                    bid_cents=None,
                    response_ms=int(bid_window_s * 1000),
                    status_code=None,
                    body=None,
                    error=error,
                )
            )

    return responses


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
        and _valid_bid_for_buyer(buyers_by_id[r.buyer_id], r.bid_cents, damage_tier)
        and _buyer_can_afford_bid(buyers_by_id[r.buyer_id], r.bid_cents)
    ]
    if not accepting:
        return None
    # highest bid wins. ties broken by lowest response time (fastest buyer).
    accepting.sort(key=lambda r: (-(r.bid_cents or 0), r.response_ms))
    winner = accepting[0]
    return winner, buyers_by_id[winner.buyer_id]


def _buyer_can_afford_bid(buyer: Buyer, bid_cents: int | None) -> bool:
    if bid_cents is None or bid_cents <= 0:
        return False
    return buyer.deposit_balance >= Decimal(bid_cents) / Decimal(100)


def _debit_amount(bid_cents: int) -> Decimal:
    return Decimal(bid_cents) / Decimal(100)


async def _reserve_buyer_wallet(
    buyer_id: UUID,
    lead_id: UUID,
    bid_cents: int,
) -> bool:
    if bid_cents <= 0:
        return False
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
    delivery_idempotency_key: str,
) -> tuple[bool, int | None, str | None]:
    """deliver full lead with PII to winning buyer. signed."""
    if not _buyer_delivery_allowed(buyer.webhook_url):
        return (False, None, "commercial_launch_not_approved")
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
            "damage_type": lead.damage_type,
            "urgency": lead.urgency,
            "damage_summary": lead.damage_summary,
            "visible_risk_level": lead.visible_risk_level,
            "estimated_job_size": lead.estimated_job_size,
            "buyer_notes": lead.buyer_notes,
            "safety_flags": sorted(set(lead.safety_flags)),
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
        "Idempotency-Key": delivery_idempotency_key,
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
    async with _lead_auction_lock(lead.id):
        return await _run_auction_locked(lead)


async def _run_auction_locked(lead: Lead) -> PingPostResult:
    """run a full ping-post cycle for one lead. returns the result."""
    bind_correlation_id(str(lead.id))
    started = time.perf_counter()
    allowed, reason = _lead_can_enter_auction(lead)
    if not allowed:
        await _persist_unauctionable_lead(lead, reason)
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

    existing_sale = await _sold_delivery_for_lead(lead.id)
    if existing_sale is not None:
        log.info(
            "auction.idempotent_sold_skip",
            lead_id=str(lead.id),
            buyer_id=str(existing_sale.buyer_id),
        )
        return PingPostResult(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            lead_id=lead.id,
            pinged_buyer_ids=[],
            winning_buyer_id=existing_sale.buyer_id,
            winning_bid_cents=existing_sale.bid_cents,
            duration_ms=int((time.perf_counter() - started) * 1000),
            damage_tier=lead.damage_tier,
        )

    try:
        buyers = await _select_eligible_buyers(lead)
    except ExclusiveZipOwnerNotReadyError as exc:
        reason = str(exc)
        await _persist_unauctionable_lead(lead, reason)
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

    async with httpx.AsyncClient() as client:

        async def bounded(b: Buyer) -> PingResponse:
            async with sem:
                return await _ping_one(client, b, payload)

        # bid window: keep completed bids, cancel only buyers still pending after BID_WINDOW_S.
        responses = await _collect_bid_window_responses(
            lead_id=lead.id, buyers=buyers, ping_buyer=bounded
        )

        await _record_pings(lead.id, payload, responses)

        winner_pair = _pick_winner(responses, buyers_by_id, lead.damage_tier)
        winning_buyer_id: UUID | None = None
        winning_bid: int | None = None

        if winner_pair:
            ping_resp, buyer = winner_pair
            bid_cents = ping_resp.bid_cents or 0
            delivery_idempotency_key = _delivery_idempotency_key(lead.id, buyer.id, bid_cents)
            existing_delivery = await _delivery_result_by_key(delivery_idempotency_key)
            if existing_delivery is not None:
                log.info(
                    "delivery.idempotent_key_skip",
                    lead_id=str(lead.id),
                    buyer_id=str(buyer.id),
                    post_result_id=str(existing_delivery.id),
                )
                return PingPostResult(
                    event_id=uuid4(),
                    occurred_at=datetime.now(UTC),
                    lead_id=lead.id,
                    pinged_buyer_ids=[b.id for b in buyers],
                    winning_buyer_id=buyer.id if existing_delivery.delivered else None,
                    winning_bid_cents=bid_cents if existing_delivery.delivered else None,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    damage_tier=lead.damage_tier,
                )
            reserved = await _reserve_buyer_wallet(buyer.id, lead.id, bid_cents)
            if reserved:
                winning_buyer_id = buyer.id
                winning_bid = bid_cents
                ok, status, body = await _post_to_winner(
                    client, buyer, lead, bid_cents, delivery_idempotency_key
                )
            else:
                ok, status, body = False, None, "buyer wallet/status changed before post"

            async with get_session() as s:
                s.add(
                    PostResult(
                        lead_id=lead.id,
                        buyer_id=buyer.id,
                        delivery_idempotency_key=delivery_idempotency_key,
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
                            amount_cents=bid_cents,
                            metadata_json={
                                "reserved_cents": bid_cents,
                                "post_result_status_code": status,
                                "exclusive": True,
                                "delivery_idempotency_key": delivery_idempotency_key,
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
