"""ping-post http api + hatchet workflow worker.

http api:
  POST /v1/auction       sync auction for one lead (test/debug)
  GET  /healthz          liveness
  GET  /readyz           readiness (db reachable)

hatchet workflow:
  ping_post_auction      durable; called by form-receiver and storm-watcher
                         retries with exponential backoff on transient errors
                         saga state lives in postgres (hatchet's home)
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from hatchet_sdk import Context, Hatchet
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from stormlead_core import BuyerStatus, Lead, configure_logging, get_logger
from stormlead_db import BillingEvent, BuyerRow, LeadRow, PostResult, get_session

from ping_post.auction import run_auction

configure_logging()
log = get_logger(__name__)

VALID_RETURN_REASONS = {
    "wrong_number",
    "duplicate",
    "outside_service_area",
    "renter_no_authority",
    "spam",
    "job_already_completed",
}


class BuyerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    contact_email: str = Field(min_length=3, max_length=255)
    contact_phone_e164: str = Field(min_length=8, max_length=20)
    webhook_url: str = Field(min_length=8)
    webhook_secret: str = Field(min_length=16)
    bid_per_lead_t1_t2: Decimal = Field(gt=Decimal("0"))
    bid_per_lead_t3: Decimal = Field(gt=Decimal("0"))
    bid_per_call: Decimal = Field(gt=Decimal("0"))
    filter_expression: str = Field(min_length=1)
    daily_cap: int = Field(default=25, ge=1, le=500)
    monthly_budget: Decimal = Field(default=Decimal("5000.00"), ge=Decimal("0"))
    deposit_balance: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    license_number: str | None = Field(default=None, max_length=128)
    license_state: str | None = Field(default=None, max_length=2)

    @field_validator("contact_phone_e164")
    @classmethod
    def phone_must_be_e164(cls, value: str) -> str:
        if not value.startswith("+"):
            raise ValueError("contact_phone_e164 must start with +")
        return value

    @field_validator("license_state")
    @classmethod
    def license_state_uppercase(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class DepositRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    external_reference: str | None = Field(default=None, max_length=255)


class ReturnLeadRequest(BaseModel):
    reason: str = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_be_valid(cls, value: str) -> str:
        if value not in VALID_RETURN_REASONS:
            allowed = ", ".join(sorted(VALID_RETURN_REASONS))
            raise ValueError(f"reason must be one of: {allowed}")
        return value


hatchet = Hatchet(debug=False)


@hatchet.workflow(on_events=["lead.qualified", "lead.captured"])
class PingPostWorkflow:
    """fired on lead.qualified (prod path: agent-runtime qualified the lead)
    or lead.captured (dev/smoke path: form-receiver emits straight through
    while agent-runtime's qualify body is still a stub).

    upstream emitters: form-receiver (after consent + dedup), agent-runtime
    (after qualification scoring). both push the event directly via the
    hatchet python sdk; no nats bridge.
    """

    @hatchet.step(timeout="30s", retries=3)
    async def auction(self, context: Context) -> dict[str, Any]:
        payload = context.workflow_input()
        lead_id = payload["lead_id"]

        async with get_session() as s:
            row = await s.get(LeadRow, lead_id)
            if row is None:
                raise ValueError(f"lead {lead_id} not found")
            lead = _row_to_lead(row)

        result = await run_auction(lead)
        return {
            "lead_id": str(result.lead_id),
            "pinged": len(result.pinged_buyer_ids),
            "winning_buyer_id": str(result.winning_buyer_id) if result.winning_buyer_id else None,
            "winning_bid_cents": result.winning_bid_cents,
            "duration_ms": result.duration_ms,
        }


def _row_to_lead(row: LeadRow) -> Lead:
    """sqlalchemy row -> pydantic model. small adapter, not a repo."""
    from stormlead_core.models import DamageTier, LeadSource, LeadStatus

    return Lead(
        id=row.id,
        source=LeadSource(row.source),
        status=LeadStatus(row.status),
        name=row.name,
        phone_e164=row.phone_e164,
        email=row.email,
        address_line1=row.address_line1,
        city=row.city,
        state=row.state,
        zip=row.zip,
        storm_id=row.storm_id,
        damage_description=row.damage_description,
        damage_tier=DamageTier(row.damage_tier) if row.damage_tier else None,
        photo_s3_keys=row.photo_s3_keys or [],
        consent_text=row.consent_text,
        consent_ip=row.consent_ip,
        consent_user_agent=row.consent_user_agent,
        consent_at=row.consent_at,
        page_url=row.page_url,
        page_html_hash=row.page_html_hash,
        rrweb_session_s3_key=row.rrweb_session_s3_key,
        trustedform_cert_url=row.trustedform_cert_url,
        property_avm=row.property_avm,
        year_built=row.year_built,
        owner_occupied=row.owner_occupied,
        qualification_score=row.qualification_score,
        rejection_reason=row.rejection_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    # start hatchet worker in background
    worker = hatchet.worker("ping-post-worker", max_runs=10)
    worker.register_workflow(PingPostWorkflow())
    task = asyncio.create_task(worker.async_start())
    log.info("startup.complete")
    try:
        yield
    finally:
        task.cancel()
        log.info("shutdown.complete")


app = FastAPI(title="stormlead ping-post", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    # cheap connectivity check
    try:
        async with get_session() as s:
            await s.execute("SELECT 1")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"db: {e}") from e
    return {"status": "ready"}


@app.post("/v1/auction")
async def trigger_auction(payload: dict[str, Any]) -> dict[str, Any]:
    """sync auction. for testing only — production goes through hatchet."""
    lead_id = payload.get("lead_id")
    if not lead_id:
        raise HTTPException(400, "lead_id required")
    try:
        async with get_session() as s:
            row = await s.get(LeadRow, lead_id)
            if row is None:
                raise HTTPException(404, "lead not found; verify the lead id and try again")
            lead = _row_to_lead(row)
        result = await run_auction(lead)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error("auction.trigger_failed", error=str(e))
        raise HTTPException(500, "auction failed; retry after checking buyer and database health") from e
    return {
        "lead_id": str(result.lead_id),
        "pinged_buyer_ids": [str(b) for b in result.pinged_buyer_ids],
        "winning_buyer_id": str(result.winning_buyer_id) if result.winning_buyer_id else None,
        "winning_bid_cents": result.winning_bid_cents,
        "duration_ms": result.duration_ms,
    }


@app.post("/v1/buyers")
async def create_buyer(payload: BuyerCreateRequest) -> dict[str, Any]:
    buyer = BuyerRow(
        name=payload.name,
        company=payload.company,
        contact_email=payload.contact_email,
        contact_phone_e164=payload.contact_phone_e164,
        status=BuyerStatus.PENDING_VERIFICATION.value,
        license_number=payload.license_number,
        license_state=payload.license_state,
        webhook_url=payload.webhook_url,
        webhook_secret=payload.webhook_secret,
        bid_per_lead_t1_t2=payload.bid_per_lead_t1_t2,
        bid_per_lead_t3=payload.bid_per_lead_t3,
        bid_per_call=payload.bid_per_call,
        filter_expression=payload.filter_expression,
        daily_cap=payload.daily_cap,
        monthly_budget=payload.monthly_budget,
        deposit_balance=payload.deposit_balance,
    )
    try:
        async with get_session() as s:
            s.add(buyer)
            await s.flush()
            if payload.deposit_balance > Decimal("0"):
                s.add(
                    BillingEvent(
                        buyer_id=buyer.id,
                        lead_id=None,
                        event_type="deposit.added",
                        amount_cents=_decimal_to_cents(payload.deposit_balance),
                        metadata_json={"source": "buyer_create"},
                    )
                )
    except Exception as e:  # noqa: BLE001
        log.error("buyer.create_failed", error=str(e))
        raise HTTPException(500, "buyer could not be created; verify the request and retry") from e
    return _buyer_wallet_response(buyer)


@app.get("/v1/buyers/{buyer_id}/wallet")
async def get_wallet(buyer_id: UUID) -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            return _buyer_wallet_response(buyer)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error("buyer.wallet_lookup_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(500, "wallet could not be loaded; retry after checking database health") from e


@app.post("/v1/buyers/{buyer_id}/deposits")
async def add_deposit(buyer_id: UUID, payload: DepositRequest) -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            amount = Decimal(payload.amount_cents) / Decimal(100)
            buyer.deposit_balance += amount
            s.add(
                BillingEvent(
                    buyer_id=buyer.id,
                    lead_id=None,
                    event_type="deposit.added",
                    amount_cents=payload.amount_cents,
                    metadata_json={"external_reference": payload.external_reference},
                )
            )
            await s.flush()
            return _buyer_wallet_response(buyer)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error("buyer.deposit_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(500, "deposit could not be recorded; retry before routing more leads") from e


@app.post("/v1/leads/{lead_id}/return")
async def return_lead(lead_id: UUID, payload: ReturnLeadRequest) -> dict[str, Any]:
    try:
        async with get_session() as s:
            result = (
                await s.execute(
                    select(PostResult)
                    .where(PostResult.lead_id == lead_id, PostResult.delivered.is_(True))
                    .order_by(PostResult.created_at.desc())
                )
            ).scalars().first()
            if result is None:
                raise HTTPException(404, "delivered lead sale not found; verify the lead id and try again")
            if result.returned:
                raise HTTPException(409, "lead was already returned; check the existing return record")
            buyer = await s.get(BuyerRow, result.buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer for this lead sale was not found; contact support")
            credit = Decimal(result.bid_cents) / Decimal(100)
            buyer.deposit_balance += credit
            buyer.lifetime_spend -= credit
            result.returned = True
            result.return_reason = payload.reason
            s.add(
                BillingEvent(
                    buyer_id=result.buyer_id,
                    lead_id=lead_id,
                    event_type="lead.returned",
                    amount_cents=result.bid_cents,
                    metadata_json={"reason": payload.reason, "notes": payload.notes},
                )
            )
            await s.flush()
            return {
                "lead_id": str(lead_id),
                "buyer_id": str(result.buyer_id),
                "credited_cents": result.bid_cents,
                "return_reason": payload.reason,
                "wallet": _buyer_wallet_response(buyer),
            }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error("lead.return_failed", lead_id=str(lead_id), error=str(e))
        raise HTTPException(500, "lead return could not be recorded; retry or contact support") from e


def _decimal_to_cents(amount: Decimal) -> int:
    return int(amount * Decimal(100))


def _buyer_wallet_response(buyer: BuyerRow) -> dict[str, Any]:
    return {
        "buyer_id": str(buyer.id),
        "company": buyer.company,
        "status": buyer.status,
        "deposit_balance_cents": _decimal_to_cents(buyer.deposit_balance),
        "lifetime_spend_cents": _decimal_to_cents(buyer.lifetime_spend),
        "daily_cap": buyer.daily_cap,
        "monthly_budget_cents": _decimal_to_cents(buyer.monthly_budget),
    }
