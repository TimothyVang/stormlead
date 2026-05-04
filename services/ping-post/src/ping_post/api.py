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
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from hatchet_sdk import Context, Hatchet
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from stormlead_core import BuyerSalesStage, BuyerStatus, Lead, configure_logging, get_logger
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

os.environ.setdefault(
    "HATCHET_CLIENT_TOKEN",
    "eyJhbGciOiJub25lIn0.eyJzdWIiOiJkZXYiLCJzZXJ2ZXJfdXJsIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwIiwiZ3JwY19icm9hZGNhc3RfYWRkcmVzcyI6ImxvY2FsaG9zdDo3MDc3In0.",
)
os.environ.setdefault("HATCHET_CLIENT_HOST_PORT", "localhost:7077")
os.environ.setdefault("HATCHET_CLIENT_TLS_STRATEGY", "none")


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
    sales_stage: BuyerSalesStage = BuyerSalesStage.PROSPECT
    notes: str | None = Field(default=None, max_length=5000)
    next_follow_up_at: datetime | None = None
    services: list[str] = Field(default_factory=list)
    target_zips: list[str] = Field(default_factory=list)
    exclusive_zips: list[str] = Field(default_factory=list)
    low_balance_threshold: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    zip_allowlist: list[str] = Field(default_factory=list)
    zip_exclusive: list[str] = Field(default_factory=list)
    monthly_cap: int | None = Field(default=None, ge=1)
    is_paused: bool = False
    pause_ping: bool = False
    pause_post: bool = False
    sla_response_ms: int | None = Field(default=None, ge=1)
    sla_post_within_seconds: int | None = Field(default=None, ge=1)

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

    @field_validator("services", "target_zips", "exclusive_zips", "zip_allowlist", "zip_exclusive")
    @classmethod
    def normalize_string_list(cls, value: list[str]) -> list[str]:
        return _normalize_string_list(value)


class BuyerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    company: str | None = Field(default=None, min_length=1, max_length=255)
    contact_email: str | None = Field(default=None, min_length=3, max_length=255)
    contact_phone_e164: str | None = Field(default=None, min_length=8, max_length=20)
    status: BuyerStatus | None = None
    webhook_url: str | None = Field(default=None, min_length=8)
    webhook_secret: str | None = Field(default=None, min_length=16)
    bid_per_lead_t1_t2: Decimal | None = Field(default=None, gt=Decimal("0"))
    bid_per_lead_t3: Decimal | None = Field(default=None, gt=Decimal("0"))
    bid_per_call: Decimal | None = Field(default=None, gt=Decimal("0"))
    filter_expression: str | None = Field(default=None, min_length=1)
    daily_cap: int | None = Field(default=None, ge=1, le=500)
    monthly_budget: Decimal | None = Field(default=None, ge=Decimal("0"))
    license_number: str | None = Field(default=None, max_length=128)
    license_state: str | None = Field(default=None, max_length=2)
    sales_stage: BuyerSalesStage | None = None
    notes: str | None = Field(default=None, max_length=5000)
    next_follow_up_at: datetime | None = None
    services: list[str] | None = None
    target_zips: list[str] | None = None
    exclusive_zips: list[str] | None = None
    low_balance_threshold: Decimal | None = Field(default=None, ge=Decimal("0"))
    zip_allowlist: list[str] | None = None
    zip_exclusive: list[str] | None = None
    monthly_cap: int | None = Field(default=None, ge=1)
    is_paused: bool | None = None
    pause_ping: bool | None = None
    pause_post: bool | None = None
    sla_response_ms: int | None = Field(default=None, ge=1)
    sla_post_within_seconds: int | None = Field(default=None, ge=1)

    @field_validator("contact_phone_e164")
    @classmethod
    def phone_must_be_e164(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("+"):
            raise ValueError("contact_phone_e164 must start with +")
        return value

    @field_validator("license_state")
    @classmethod
    def license_state_uppercase(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("services", "target_zips", "exclusive_zips", "zip_allowlist", "zip_exclusive")
    @classmethod
    def normalize_optional_string_list(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_string_list(value) if value is not None else None


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
_supports_legacy_hatchet_worker = hasattr(hatchet, "step")


async def _auction_step(context: Context) -> dict[str, Any]:
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


if _supports_legacy_hatchet_worker:

    @hatchet.workflow(name="ping-post-auction", on_events=["lead.qualified", "lead.captured"])
    class PingPostWorkflow:
        """Hatchet SDK v0.x workflow wrapper."""

        @hatchet.step(timeout="30s", retries=3)
        async def auction(self, context: Context) -> dict[str, Any]:
            return await _auction_step(context)

else:

    class PingPostWorkflow:
        """Placeholder so the API imports under Hatchet SDK versions with a different worker API."""

        async def auction(self, context: Context) -> dict[str, Any]:
            return await _auction_step(context)


def _row_to_lead(row: LeadRow) -> Lead:
    """sqlalchemy row -> pydantic model. small adapter, not a repo."""
    from stormlead_core.models import DamageTier, LeadClass, LeadSource, LeadStatus

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
        lead_class=LeadClass(row.lead_class) if row.lead_class else None,
        qualification_reason=row.qualification_reason,
        requested_service=row.requested_service,
        campaign_id=row.campaign_id,
        campaign_source=row.campaign_source,
        first_touch_source=row.first_touch_source,
        last_touch_source=row.last_touch_source,
        rejection_reason=row.rejection_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task: asyncio.Task | None = None
    if _supports_legacy_hatchet_worker:
        worker = hatchet.worker("ping-post-worker", max_runs=10)
        worker.register_workflow(PingPostWorkflow())
        task = asyncio.create_task(worker.async_start())
    else:
        log.warning("hatchet.worker_skipped", reason="unsupported_sdk_api")
    log.info("startup.complete")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
        log.info("shutdown.complete")


app = FastAPI(title="stormlead ping-post", lifespan=lifespan)


@app.get("/admin", response_class=HTMLResponse)
async def admin() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>StormLead Admin</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }
    h1 { margin-bottom: 0.25rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
    .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: .8rem; }
    .card, table, form, .panel { background: #111827; border: 1px solid #334155; border-radius: 12px; }
    .card { padding: 1rem; }
    .metric { font-size: 1.8rem; font-weight: 700; color: #38bdf8; }
    form, .panel { padding: 1rem; margin: 1rem 0; }
    label { display: grid; gap: .35rem; color: #bfdbfe; font-size: .9rem; }
    input, select, textarea { background: #020617; border: 1px solid #475569; border-radius: 8px; color: #e2e8f0; padding: .65rem; }
    textarea { min-height: 4rem; }
    button { background: #0284c7; border: 0; border-radius: 10px; color: white; cursor: pointer; font-weight: 700; padding: .8rem 1rem; }
    button.secondary { background: #334155; }
    button:hover { filter: brightness(1.08); }
    .actions { display: flex; flex-wrap: wrap; gap: .75rem; margin-top: 1rem; }
    .status { border-left: 4px solid #38bdf8; margin: 1rem 0; padding: .75rem 1rem; white-space: pre-wrap; }
    table { width: 100%; border-collapse: collapse; overflow: hidden; }
    th, td { padding: 0.75rem; border-bottom: 1px solid #334155; text-align: left; }
    th { color: #93c5fd; }
  </style>
</head>
<body>
  <h1>StormLead Admin</h1>
  <p>Paid-pilot control surface</p>
  <section class="grid" id="kpis"></section>
  <section class="panel" aria-label="cowork workflow controls">
    <h2>Cowork Workflow Controls</h2>
    <p>Create a real buyer, activate/fund it, then verify dashboard KPIs and roster state.</p>
    <div class="status" id="workflow-status">Ready. No mock data is used.</div>
  </section>

  <form id="buyer-form" aria-label="create buyer form">
    <h2>Create Buyer</h2>
    <div class="form-grid">
      <label>Name <input name="name" value="Cowork Buyer" required /></label>
      <label>Company <input name="company" value="Cowork Tree Pros" required /></label>
      <label>Email <input name="contact_email" value="ops@cowork-tree.example" required /></label>
      <label>Phone <input name="contact_phone_e164" value="+15125550199" required /></label>
      <label>Webhook URL <input name="webhook_url" value="http://host.docker.internal:9999/cowork-buyer" required /></label>
      <label>Webhook Secret <input name="webhook_secret" value="cowork-secret-minimum-16" required /></label>
      <label>Tier 1/2 Bid <input name="bid_per_lead_t1_t2" value="75.00" required /></label>
      <label>Tier 3 Bid <input name="bid_per_lead_t3" value="175.00" required /></label>
      <label>Call Bid <input name="bid_per_call" value="100.00" required /></label>
      <label>Filter <input name="filter_expression" value="lead.state == 'TX'" required /></label>
      <label>Daily Cap <input name="daily_cap" value="25" required /></label>
      <label>Monthly Budget <input name="monthly_budget" value="5000.00" required /></label>
      <label>Initial Deposit <input name="deposit_balance" value="0.00" required /></label>
      <label>Services <input name="services" value="tree_removal" required /></label>
      <label>Target Zips <input name="target_zips" value="78701,78702" required /></label>
      <label>Exclusive Zips <input name="exclusive_zips" value="" /></label>
      <label>Low Balance Threshold <input name="low_balance_threshold" value="150.00" required /></label>
      <label>Notes <textarea name="notes">Created from the real StormLead admin UI.</textarea></label>
    </div>
    <div class="actions">
      <button type="submit">Create Real Buyer</button>
    </div>
  </form>

  <form id="buyer-update-form" aria-label="update buyer form">
    <h2>Activate / Fund Buyer</h2>
    <div class="form-grid">
      <label>Buyer ID <input name="buyer_id" id="selected-buyer-id" required /></label>
      <label>Status
        <select name="status"><option value="active">active</option><option value="paused">paused</option><option value="pending_verification">pending_verification</option></select>
      </label>
      <label>Sales Stage
        <select name="sales_stage"><option value="funded">funded</option><option value="prospect">prospect</option><option value="contacted">contacted</option><option value="agreement_sent">agreement_sent</option></select>
      </label>
      <label>Services <input name="services" value="tree_removal" /></label>
      <label>Target Zips <input name="target_zips" value="78701,78702" /></label>
    </div>
    <div class="actions">
      <button type="submit">Update Real Buyer</button>
    </div>
  </form>

  <form id="deposit-form" aria-label="deposit form">
    <h2>Add Deposit</h2>
    <div class="form-grid">
      <label>Buyer ID <input name="buyer_id" id="deposit-buyer-id" required /></label>
      <label>Amount Cents <input name="amount_cents" value="77700" required /></label>
      <label>Reference <input name="external_reference" value="playwright-cowork-real-ui" /></label>
    </div>
    <div class="actions">
      <button type="submit">Add Real Deposit</button>
      <button type="button" class="secondary" onclick="load()">Refresh Dashboard</button>
    </div>
  </form>

  <h2>Buyers</h2>
  <table aria-label="buyers">
    <thead><tr><th>Company</th><th>Status</th><th>Stage</th><th>Wallet</th><th>Services</th><th>Zips</th><th>Low Balance</th><th>ID</th></tr></thead>
    <tbody id="buyers"></tbody>
  </table>
  <script>
    const money = cents => `$${(cents / 100).toFixed(2)}`;
    const statusBox = document.querySelector('#workflow-status');
    const setStatus = msg => { statusBox.textContent = msg; };
    const list = value => value.split(',').map(v => v.trim()).filter(Boolean);
    const formJson = form => Object.fromEntries(new FormData(form).entries());
    const api = async (path, options = {}) => {
      const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
      const text = await res.text();
      const data = text ? JSON.parse(text) : {};
      if (!res.ok) throw new Error(`${res.status}: ${JSON.stringify(data)}`);
      return data;
    };

    async function load() {
      const [summaryRes, buyersRes] = await Promise.all([
        fetch('/v1/admin/kpis'),
        fetch('/v1/buyers'),
      ]);
      const summary = await summaryRes.json();
      const buyers = await buyersRes.json();
      document.querySelector('#kpis').innerHTML = [
        ['Prepaid cash', money(summary.prepaid_cash_cents)],
        ['Active buyers', summary.active_buyers],
        ['Sold leads', summary.sold_leads],
        ['Returned leads', summary.returned_leads],
        ['Lead revenue', money(summary.lead_revenue_cents)],
      ].map(([label, value]) => `<div class="card"><div>${label}</div><div class="metric">${value}</div></div>`).join('');
      document.querySelector('#buyers').innerHTML = buyers.buyers.map(b => `
        <tr data-buyer-id="${b.buyer_id}">
          <td>${b.company}</td><td>${b.status}</td><td>${b.sales_stage}</td>
          <td>${money(b.deposit_balance_cents)}</td><td>${b.services.join(', ')}</td>
          <td>${b.target_zips.join(', ')}</td><td>${money(b.low_balance_threshold_cents)}</td><td>${b.buyer_id}</td>
        </tr>`).join('');
      setStatus(`Dashboard loaded from real APIs. Buyers: ${buyers.buyers.length}`);
    }

    document.querySelector('#buyer-form').addEventListener('submit', async event => {
      event.preventDefault();
      const raw = formJson(event.currentTarget);
      setStatus('Creating real buyer through POST /v1/buyers...');
      const buyer = await api('/v1/buyers', {
        method: 'POST',
        body: JSON.stringify({
          ...raw,
          services: list(raw.services),
          target_zips: list(raw.target_zips),
          exclusive_zips: list(raw.exclusive_zips || ''),
        }),
      });
      document.querySelector('#selected-buyer-id').value = buyer.buyer_id;
      document.querySelector('#deposit-buyer-id').value = buyer.buyer_id;
      await load();
      setStatus(`Created real buyer ${buyer.company} (${buyer.buyer_id}).`);
    });

    document.querySelector('#buyer-update-form').addEventListener('submit', async event => {
      event.preventDefault();
      const raw = formJson(event.currentTarget);
      setStatus(`Updating real buyer ${raw.buyer_id} through PATCH /v1/buyers/{id}...`);
      const buyer = await api(`/v1/buyers/${raw.buyer_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          status: raw.status,
          sales_stage: raw.sales_stage,
          services: list(raw.services),
          target_zips: list(raw.target_zips),
        }),
      });
      await load();
      setStatus(`Updated real buyer ${buyer.company}: ${buyer.status}/${buyer.sales_stage}.`);
    });

    document.querySelector('#deposit-form').addEventListener('submit', async event => {
      event.preventDefault();
      const raw = formJson(event.currentTarget);
      setStatus(`Adding real deposit through POST /v1/buyers/${raw.buyer_id}/deposits...`);
      const wallet = await api(`/v1/buyers/${raw.buyer_id}/deposits`, {
        method: 'POST',
        body: JSON.stringify({
          amount_cents: Number(raw.amount_cents),
          external_reference: raw.external_reference,
        }),
      });
      await load();
      setStatus(`Deposit recorded. New wallet: ${money(wallet.deposit_balance_cents)}.`);
    });

    load().catch(err => {
      document.body.insertAdjacentHTML('beforeend', `<pre role="alert">${err}</pre>`);
    });
  </script>
</body>
</html>
"""


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    # cheap connectivity check
    try:
        async with get_session() as s:
            await s.execute("SELECT 1")
    except Exception as e:
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
    except Exception as e:
        log.error("auction.trigger_failed", error=str(e))
        raise HTTPException(
            500, "auction failed; retry after checking buyer and database health"
        ) from e
    return {
        "lead_id": str(result.lead_id),
        "pinged_buyer_ids": [str(b) for b in result.pinged_buyer_ids],
        "winning_buyer_id": str(result.winning_buyer_id) if result.winning_buyer_id else None,
        "winning_bid_cents": result.winning_bid_cents,
        "duration_ms": result.duration_ms,
    }


@app.post("/v1/buyers")
async def create_buyer(payload: BuyerCreateRequest) -> dict[str, Any]:
    await _assert_no_exclusive_zip_conflict(payload.exclusive_zips)
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
        sales_stage=payload.sales_stage.value,
        notes=payload.notes,
        next_follow_up_at=payload.next_follow_up_at,
        services=payload.services,
        target_zips=payload.target_zips,
        exclusive_zips=payload.exclusive_zips,
        zip_allowlist=payload.zip_allowlist,
        zip_exclusive=payload.zip_exclusive,
        low_balance_threshold=payload.low_balance_threshold,
        monthly_cap=payload.monthly_cap,
        is_paused=payload.is_paused,
        pause_ping=payload.pause_ping,
        pause_post=payload.pause_post,
        sla_response_ms=payload.sla_response_ms,
        sla_post_within_seconds=payload.sla_post_within_seconds,
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
    except Exception as e:
        log.error("buyer.create_failed", error=str(e))
        raise HTTPException(500, "buyer could not be created; verify the request and retry") from e
    return _buyer_response(buyer)


@app.get("/v1/buyers")
async def list_buyers() -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyers = (
                (await s.execute(select(BuyerRow).order_by(BuyerRow.created_at.desc())))
                .scalars()
                .all()
            )
            return {"buyers": [_buyer_response(buyer) for buyer in buyers]}
    except Exception as e:
        log.error("buyer.list_failed", error=str(e))
        raise HTTPException(
            500, "buyers could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/admin/kpis")
async def admin_kpis() -> dict[str, Any]:
    try:
        async with get_session() as s:
            prepaid = await s.scalar(select(func.coalesce(func.sum(BuyerRow.deposit_balance), 0)))
            active_buyers = await s.scalar(
                select(func.count(BuyerRow.id)).where(BuyerRow.status == BuyerStatus.ACTIVE.value)
            )
            sold_leads = await s.scalar(
                select(func.count(PostResult.id)).where(PostResult.delivered.is_(True))
            )
            returned_leads = await s.scalar(
                select(func.count(PostResult.id)).where(PostResult.returned.is_(True))
            )
            lead_revenue = await s.scalar(
                select(func.coalesce(func.sum(PostResult.bid_cents), 0)).where(
                    PostResult.delivered.is_(True),
                    PostResult.returned.is_(False),
                )
            )
        return {
            "prepaid_cash_cents": _decimal_to_cents(Decimal(prepaid or 0)),
            "active_buyers": int(active_buyers or 0),
            "sold_leads": int(sold_leads or 0),
            "returned_leads": int(returned_leads or 0),
            "lead_revenue_cents": int(lead_revenue or 0),
        }
    except Exception as e:
        log.error("admin.kpis_failed", error=str(e))
        raise HTTPException(
            500, "admin kpis could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/buyers/{buyer_id}")
async def get_buyer(buyer_id: UUID) -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            return _buyer_response(buyer)
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.lookup_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(
            500, "buyer could not be loaded; retry after checking database health"
        ) from e


@app.patch("/v1/buyers/{buyer_id}")
async def update_buyer(buyer_id: UUID, payload: BuyerUpdateRequest) -> dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    if "exclusive_zips" in updates:
        await _assert_no_exclusive_zip_conflict(
            updates["exclusive_zips"], exclude_buyer_id=buyer_id
        )
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            for key, value in updates.items():
                if isinstance(value, (BuyerStatus, BuyerSalesStage)):
                    value = value.value
                setattr(buyer, key, value)
            await s.flush()
            return _buyer_response(buyer)
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.update_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(500, "buyer could not be updated; verify the request and retry") from e


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
    except Exception as e:
        log.error("buyer.wallet_lookup_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(
            500, "wallet could not be loaded; retry after checking database health"
        ) from e


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
    except Exception as e:
        log.error("buyer.deposit_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(
            500, "deposit could not be recorded; retry before routing more leads"
        ) from e


@app.patch("/v1/admin/buyers/{buyer_id}/constraints")
async def update_buyer_constraints(buyer_id: UUID, payload: BuyerUpdateRequest) -> dict[str, Any]:
    return await update_buyer(buyer_id, payload)


@app.get("/v1/admin/eligibility-health")
async def eligibility_health() -> dict[str, Any]:
    async with get_session() as s:
        buyers = (await s.execute(select(BuyerRow))).scalars().all()
        unhealthy = []
        for b in buyers:
            reasons = []
            if b.is_paused or b.pause_ping:
                reasons.append("paused")
            if b.status != BuyerStatus.ACTIVE.value:
                reasons.append("not_active")
            if b.deposit_balance <= b.low_balance_threshold:
                reasons.append("low_balance")
            if reasons:
                unhealthy.append({"buyer_id": str(b.id), "reasons": reasons})
        return {
            "total_buyers": len(buyers),
            "healthy_buyers": len(buyers) - len(unhealthy),
            "unhealthy_buyers": unhealthy,
        }


@app.post("/v1/leads/{lead_id}/return")
async def return_lead(lead_id: UUID, payload: ReturnLeadRequest) -> dict[str, Any]:
    try:
        async with get_session() as s:
            result = (
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
            if result is None:
                raise HTTPException(
                    404, "delivered lead sale not found; verify the lead id and try again"
                )
            if result.returned:
                raise HTTPException(
                    409, "lead was already returned; check the existing return record"
                )
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
    except Exception as e:
        log.error("lead.return_failed", lead_id=str(lead_id), error=str(e))
        raise HTTPException(
            500, "lead return could not be recorded; retry or contact support"
        ) from e


def _decimal_to_cents(amount: Decimal) -> int:
    return int(amount * Decimal(100))


def _normalize_string_list(values: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for value in values:
        item = value.strip().lower()
        if item and item not in seen:
            normalized.append(item)
            seen.add(item)
    return normalized


async def _assert_no_exclusive_zip_conflict(
    exclusive_zips: list[str],
    *,
    exclude_buyer_id: UUID | None = None,
) -> None:
    if not exclusive_zips:
        return
    requested = set(exclusive_zips)
    async with get_session() as s:
        rows = (
            await s.execute(select(BuyerRow.id, BuyerRow.company, BuyerRow.exclusive_zips))
        ).all()
    for buyer_id, company, existing_zips in rows:
        if exclude_buyer_id is not None and buyer_id == exclude_buyer_id:
            continue
        conflict = requested.intersection(existing_zips or [])
        if conflict:
            zips = ", ".join(sorted(conflict))
            raise HTTPException(409, f"exclusive zip conflict with {company}: {zips}")


def _buyer_response(buyer: BuyerRow) -> dict[str, Any]:
    payload = _buyer_wallet_response(buyer)
    payload.update(
        {
            "name": buyer.name,
            "contact_email": buyer.contact_email,
            "contact_phone_e164": buyer.contact_phone_e164,
            "license_number": buyer.license_number,
            "license_state": buyer.license_state,
            "license_verified_at": buyer.license_verified_at.isoformat()
            if buyer.license_verified_at
            else None,
            "sales_stage": buyer.sales_stage,
            "notes": buyer.notes,
            "next_follow_up_at": buyer.next_follow_up_at.isoformat()
            if buyer.next_follow_up_at
            else None,
            "services": buyer.services or [],
            "target_zips": buyer.target_zips or [],
            "exclusive_zips": buyer.exclusive_zips or [],
            "zip_allowlist": buyer.zip_allowlist or [],
            "zip_exclusive": buyer.zip_exclusive or [],
            "low_balance_threshold_cents": _decimal_to_cents(buyer.low_balance_threshold),
            "monthly_cap": buyer.monthly_cap,
            "is_paused": buyer.is_paused,
            "pause_ping": buyer.pause_ping,
            "pause_post": buyer.pause_post,
            "sla_response_ms": buyer.sla_response_ms,
            "sla_post_within_seconds": buyer.sla_post_within_seconds,
            "filter_expression": buyer.filter_expression,
            "webhook_url": buyer.webhook_url,
        }
    )
    return payload


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
