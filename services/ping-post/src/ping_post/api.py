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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from hatchet_sdk import Context, Hatchet
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Integer, and_, func, select, text
from stormlead_core import (
    BuyerSalesStage,
    BuyerStatus,
    Lead,
    PipelineState,
    configure_logging,
    get_logger,
)
from stormlead_db import (
    BillingEvent,
    BuyerRow,
    LeadRow,
    LeadStateTransition,
    PingAttempt,
    PostResult,
    build_transition_idempotency_key,
    get_session,
    latest_state,
    list_lead_timeline,
    list_recent_lead_runs,
    record_transition,
    summarize_transition_payload,
)

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
VALID_REVIEW_ACTIONS = {"approve", "hold", "review"}


class KpiThresholdConfig(BaseModel):
    pause_delivery_success_rate: float = Field(default=0.85, ge=0, le=1)
    stop_loss_return_rate: float = Field(default=0.2, ge=0, le=1)
    pause_wallet_runway_days: float = Field(default=3.0, ge=0)
    stop_loss_net_revenue_cents: int = 0
    pause_retry_error_rate: float = Field(default=0.2, ge=0, le=1)
    pause_ping_p95_latency_ms: int = Field(default=2500, ge=0)


KPI_THRESHOLDS = KpiThresholdConfig()
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

    @field_validator("services", "target_zips", "exclusive_zips")
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

    @field_validator("services", "target_zips", "exclusive_zips")
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


class LeadReviewRequest(BaseModel):
    action: str = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)
    operator: str = Field(default="local-admin", min_length=1, max_length=128)

    @field_validator("action")
    @classmethod
    def action_must_be_valid(cls, value: str) -> str:
        action = value.strip().lower()
        if action not in VALID_REVIEW_ACTIONS:
            allowed = ", ".join(sorted(VALID_REVIEW_ACTIONS))
            raise ValueError(f"action must be one of: {allowed}")
        return action


hatchet = Hatchet(debug=False)
_supports_legacy_hatchet_worker = hasattr(hatchet, "step")


async def _auction_step(context: Context) -> dict[str, Any]:
    workflow_input = context.workflow_input
    payload = workflow_input() if callable(workflow_input) else workflow_input
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

    @hatchet.workflow(name="ping-post-auction", on_events=["lead.qualified"])
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
    .muted { color: #94a3b8; }
    .mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .85rem; }
    .timeline { display: grid; gap: .75rem; margin-top: 1rem; }
    .timeline-event { background: #020617; border: 1px solid #334155; border-left: 4px solid #38bdf8; border-radius: 10px; padding: .85rem; }
    .timeline-event.review { border-left-color: #facc15; }
    .timeline-event.attention { border-left-color: #fb7185; }
    .payload { background: #0f172a; border-radius: 8px; color: #cbd5e1; overflow: auto; padding: .75rem; }
    table { width: 100%; border-collapse: collapse; overflow: hidden; }
    th, td { padding: 0.75rem; border-bottom: 1px solid #334155; text-align: left; }
    th { color: #93c5fd; }
    tr[data-lead-id] { cursor: pointer; }
    tr[data-lead-id]:hover { background: #1e293b; }
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

  <h2>Agentic Workflow KPIs</h2>
  <section class="grid" id="workflow-kpis"></section>

  <section class="panel" aria-label="workflow timeline">
    <h2>Lead Workflow Timeline</h2>
    <p class="muted">Inspect append-only state transitions, agent decisions, review actions, and redacted payload summaries from real database audit rows.</p>
    <form id="timeline-form" aria-label="load lead timeline form">
      <div class="form-grid">
        <label>Lead ID <input name="lead_id" id="timeline-lead-id" placeholder="Paste a lead UUID" /></label>
        <label>Review Notes <input name="notes" id="review-notes" value="Reviewed in StormLead admin timeline." /></label>
      </div>
      <div class="actions">
        <button type="submit">Load Timeline</button>
        <button type="button" class="secondary" id="review-hold">Hold For Review</button>
        <button type="button" class="secondary" id="review-approve">Approve / Clear Hold</button>
      </div>
    </form>
    <div id="timeline-summary" class="status">Select a lead from Recent Workflow Runs or paste a lead UUID.</div>
    <div class="timeline" id="timeline"></div>
  </section>

  <section class="panel" aria-label="recent workflow runs">
    <h2>Recent Workflow Runs</h2>
    <p class="muted">Rows are grouped from lead_state_transitions and can be opened in the timeline.</p>
    <table aria-label="workflow runs">
      <thead><tr><th>Updated</th><th>State</th><th>Status</th><th>Events</th><th>Latest Event</th><th>Lead ID</th></tr></thead>
      <tbody id="workflow-runs"></tbody>
    </table>
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
    const htmlEscapeMap = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => htmlEscapeMap[ch]);
    const list = value => value.split(',').map(v => v.trim()).filter(Boolean);
    const formJson = form => Object.fromEntries(new FormData(form).entries());
    const api = async (path, options = {}) => {
      const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
      const text = await res.text();
      const data = text ? JSON.parse(text) : {};
      if (!res.ok) throw new Error(`${res.status}: ${JSON.stringify(data)}`);
      return data;
    };

    const metricValue = metric => {
      if (metric.value === null || metric.value === undefined) return 'n/a';
      if (metric.unit === 'ratio') return `${(Number(metric.value) * 100).toFixed(1)}%`;
      if (metric.unit === 'usd') return `$${Number(metric.value).toFixed(4)}`;
      return `${metric.value}`;
    };

    const metricDetail = metric => {
      if (metric.reason) return metric.reason;
      if (metric.unit === 'ratio') return `${metric.numerator}/${metric.denominator}`;
      return metric.unit || '';
    };

    function renderWorkflowKpis(data) {
      const metrics = data.metrics || [];
      document.querySelector('#workflow-kpis').innerHTML = metrics.length ? metrics.map(metric => `
        <div class="card">
          <div>${escapeHtml(metric.label)}</div>
          <div class="metric">${escapeHtml(metricValue(metric))}</div>
          <div class="muted">${escapeHtml(metricDetail(metric))}</div>
        </div>`).join('') : '<div class="muted">No workflow KPIs are available yet.</div>';
    }

    function renderWorkflowRuns(runs) {
      const tbody = document.querySelector('#workflow-runs');
      if (!runs.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="muted">No audited lead workflow runs yet.</td></tr>';
        return;
      }
      tbody.innerHTML = runs.map(run => `
        <tr data-lead-id="${escapeHtml(run.lead_id)}">
          <td>${escapeHtml(new Date(run.updated_at).toLocaleString())}</td>
          <td>${escapeHtml(run.current_state)}</td>
          <td>${escapeHtml(run.status)}</td>
          <td>${escapeHtml(run.event_count)}</td>
          <td>${escapeHtml(run.latest_event_type)}</td>
          <td class="mono">${escapeHtml(run.lead_id)}</td>
        </tr>`).join('');
      tbody.querySelectorAll('tr[data-lead-id]').forEach(row => {
        row.addEventListener('click', async () => {
          const leadId = row.getAttribute('data-lead-id');
          document.querySelector('#timeline-lead-id').value = leadId;
          await loadTimeline(leadId);
        });
      });
    }

    function renderTimeline(data) {
      const lead = data.lead || {};
      document.querySelector('#timeline-summary').textContent = `Lead ${data.lead_id}\nCurrent state: ${data.current_state}\nStatus: ${lead.status || 'unknown'} | Service: ${lead.requested_service || 'unknown'} | Class: ${lead.lead_class || 'unknown'} | Hold: ${lead.hold_for_review ? 'yes' : 'no'}`;
      const events = data.events || [];
      document.querySelector('#timeline').innerHTML = events.length ? events.map(event => {
        const isReview = event.event_type.startsWith('admin.review');
        const attention = !['succeeded', 'reviewed'].includes(event.status);
        const classes = ['timeline-event', isReview ? 'review' : '', attention ? 'attention' : ''].filter(Boolean).join(' ');
        const payload = JSON.stringify(event.payload_summary || {}, null, 2);
        return `
          <article class="${classes}">
            <strong>${escapeHtml(event.sequence)}. ${escapeHtml(event.event_type)}</strong>
            <div class="muted">${escapeHtml(event.from_state)} -> ${escapeHtml(event.to_state)} | ${escapeHtml(event.status)} | ${escapeHtml(event.created_at)}</div>
            <div class="muted mono">${escapeHtml(event.task_name || 'manual')} ${event.workflow_run_id ? `| run ${escapeHtml(event.workflow_run_id)}` : ''}</div>
            <pre class="payload">${escapeHtml(payload)}</pre>
          </article>`;
      }).join('') : '<div class="status">This lead has no audited transition rows yet.</div>';
    }

    async function loadTimeline(leadId) {
      if (!leadId) return;
      setStatus(`Loading real audit timeline for lead ${leadId}...`);
      const data = await api(`/v1/admin/leads/${encodeURIComponent(leadId)}/timeline`);
      renderTimeline(data);
      setStatus(`Timeline loaded from lead_state_transitions. Events: ${(data.events || []).length}`);
    }

    async function load() {
      const [summary, buyers, workflowKpis, workflowRuns] = await Promise.all([
        api('/v1/admin/kpis'),
        api('/v1/buyers'),
        api('/v1/admin/workflow-kpis'),
        api('/v1/admin/workflow-runs/recent'),
      ]);
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
      renderWorkflowKpis(workflowKpis);
      renderWorkflowRuns(workflowRuns.runs || []);
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

    document.querySelector('#timeline-form').addEventListener('submit', async event => {
      event.preventDefault();
      const raw = formJson(event.currentTarget);
      await loadTimeline(raw.lead_id.trim());
    });

    async function reviewLead(action) {
      const leadId = document.querySelector('#timeline-lead-id').value.trim();
      if (!leadId) {
        setStatus('Paste or select a lead ID before recording a review action.');
        return;
      }
      const notes = document.querySelector('#review-notes').value;
      setStatus(`Recording ${action} review action for ${leadId}...`);
      await api(`/v1/admin/leads/${encodeURIComponent(leadId)}/review`, {
        method: 'POST',
        body: JSON.stringify({ action, notes, operator: 'local-admin' }),
      });
      await loadTimeline(leadId);
      await load();
      setStatus(`Review action recorded for ${leadId}. Timeline refreshed from audit rows.`);
    }

    document.querySelector('#review-hold').addEventListener('click', () => reviewLead('hold'));
    document.querySelector('#review-approve').addEventListener('click', () => reviewLead('approve'));

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
            await s.execute(text("SELECT 1"))
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
        low_balance_threshold=payload.low_balance_threshold,
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


@app.get("/v1/admin/workflow-kpis")
async def admin_workflow_kpis() -> dict[str, Any]:
    try:
        async with get_session() as s:
            transition_rows = (
                await s.execute(
                    select(LeadStateTransition.event_type, func.count(LeadStateTransition.id))
                    .select_from(LeadStateTransition)
                    .group_by(LeadStateTransition.event_type)
                )
            ).all()
            status_rows = (
                await s.execute(
                    select(LeadStateTransition.status, func.count(LeadStateTransition.id))
                    .select_from(LeadStateTransition)
                    .group_by(LeadStateTransition.status)
                )
            ).all()
            total_pings = await s.scalar(select(func.count(PingAttempt.id)))
            accepted_pings = await s.scalar(
                select(func.count(PingAttempt.id)).where(PingAttempt.accepted.is_(True))
            )
            delivered_posts = await s.scalar(
                select(func.count(PostResult.id)).where(PostResult.delivered.is_(True))
            )
            returned_posts = await s.scalar(
                select(func.count(PostResult.id)).where(PostResult.returned.is_(True))
            )
            agent_payloads = (
                (
                    await s.execute(
                        select(LeadStateTransition.payload_json).where(
                            LeadStateTransition.task_name == "agent_runtime.qualify_lead"
                        )
                    )
                )
                .scalars()
                .all()
            )

        transition_counts = {str(event): int(count) for event, count in transition_rows}
        status_counts = {str(status): int(count) for status, count in status_rows}
        captured = transition_counts.get("lead.captured", 0)
        enriched = transition_counts.get("lead.enriched", 0)
        qualified = transition_counts.get("lead.qualified", 0)
        rejected = transition_counts.get("lead.rejected", 0)
        auctioned = transition_counts.get("lead.auctioned", 0)
        sold = transition_counts.get("lead.sold", 0)
        unsold = transition_counts.get("lead.unsold", 0)
        nurtured = transition_counts.get("lead.nurtured", 0)
        agent_cost_usd = _sum_agent_cost(agent_payloads)
        cost_denominator = qualified + rejected

        return {
            "metrics": [
                _count_metric("lead_throughput", "Lead throughput", captured, "leads"),
                _ratio_metric(
                    "enrichment_success_rate",
                    "Enrichment success",
                    enriched,
                    captured,
                    "No captured leads have been audited yet",
                ),
                _ratio_metric(
                    "qualification_acceptance_rate",
                    "Qualification acceptance",
                    qualified,
                    qualified + rejected,
                    "No qualification decisions have been audited yet",
                ),
                _ratio_metric(
                    "auction_win_rate",
                    "Auction win rate",
                    sold,
                    auctioned,
                    "No auctioned leads have been audited yet",
                ),
                _ratio_metric(
                    "buyer_acceptance_rate",
                    "Buyer acceptance",
                    int(accepted_pings or 0),
                    int(total_pings or 0),
                    "No buyer pings have been recorded yet",
                ),
                _count_metric("sold_leads", "Sold leads", sold, "leads"),
                _count_metric("unsold_leads", "Unsold leads", unsold, "leads"),
                _ratio_metric(
                    "nurture_recovery_rate",
                    "Nurture recovery",
                    nurtured,
                    unsold + rejected,
                    "No unsold or rejected leads are available for nurture yet",
                ),
                _money_metric(
                    "estimated_cost_per_qualified_lead",
                    "Est. cost / qualified decision",
                    agent_cost_usd / cost_denominator if cost_denominator else None,
                    "No qualification-cost payloads have been audited yet"
                    if not cost_denominator
                    else None,
                ),
                _ratio_metric(
                    "return_rate",
                    "Return rate",
                    int(returned_posts or 0),
                    int(delivered_posts or 0),
                    "No delivered posts have been recorded yet",
                ),
            ],
            "transition_counts": transition_counts,
            "status_counts": status_counts,
        }
    except Exception as e:
        log.error("admin.workflow_kpis_failed", error=str(e))
        raise HTTPException(
            500, "workflow kpis could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/admin/workflow-runs/recent")
async def recent_workflow_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    try:
        async with get_session() as s:
            runs = await list_recent_lead_runs(s, limit=limit)
        return {"runs": [run.as_dict() for run in runs]}
    except Exception as e:
        log.error("admin.workflow_runs_failed", error=str(e))
        raise HTTPException(
            500, "workflow runs could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/admin/leads/{lead_id}/timeline")
async def lead_timeline(
    lead_id: UUID, limit: int = Query(default=100, ge=1, le=250)
) -> dict[str, Any]:
    try:
        async with get_session() as s:
            lead = await s.get(LeadRow, lead_id)
            if lead is None:
                raise HTTPException(404, "lead not found; verify the lead id and try again")
            events = await list_lead_timeline(s, lead_id, limit=limit)
            current_state = events[-1].to_state if events else lead.status
            return {
                "lead_id": str(lead_id),
                "current_state": current_state,
                "lead": _lead_admin_summary(lead),
                "events": [event.as_dict() for event in events],
            }
    except HTTPException:
        raise
    except Exception as e:
        log.error("admin.lead_timeline_failed", lead_id=str(lead_id), error=str(e))
        raise HTTPException(
            500, "lead timeline could not be loaded; retry after checking database health"
        ) from e


@app.post("/v1/admin/leads/{lead_id}/review")
async def review_lead(lead_id: UUID, payload: LeadReviewRequest) -> dict[str, Any]:
    try:
        async with get_session() as s:
            lead = await s.get(LeadRow, lead_id)
            if lead is None:
                raise HTTPException(404, "lead not found; verify the lead id and try again")
            if payload.action in {"hold", "review"}:
                lead.hold_for_review = True
            if payload.action == "approve":
                lead.hold_for_review = False

            current_state = await latest_state(s, lead_id)
            if current_state is None:
                current_state = _pipeline_state_or_captured(lead.status)
            event_type = f"admin.review.{payload.action}"
            result = await record_transition(
                s,
                lead_id=lead_id,
                from_state=None,
                to_state=current_state,
                event_type=event_type,
                task_name="admin.review_action",
                status="reviewed",
                idempotency_key=build_transition_idempotency_key(
                    lead_id=lead_id,
                    from_state=None,
                    to_state=current_state,
                    event_type=event_type,
                    task_name="admin.review_action",
                    version=f"review:{uuid4()}",
                ),
                payload={
                    "action": payload.action,
                    "operator": payload.operator,
                    "notes": payload.notes,
                    "hold_for_review": lead.hold_for_review,
                },
            )
            await s.flush()
            transition = result.transition
            return {
                "lead_id": str(lead_id),
                "action": payload.action,
                "hold_for_review": lead.hold_for_review,
                "timeline_event": {
                    "id": str(transition.id),
                    "event_type": transition.event_type,
                    "status": transition.status,
                    "payload_summary": summarize_transition_payload(transition.payload_json),
                },
            }
    except HTTPException:
        raise
    except Exception as e:
        log.error("admin.lead_review_failed", lead_id=str(lead_id), error=str(e))
        raise HTTPException(
            500, "lead review action could not be recorded; retry after checking database health"
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


def _window_clause(start_at: datetime | None, end_at: datetime | None):
    clauses = []
    if start_at is not None:
        clauses.append(LeadRow.created_at >= start_at)
    if end_at is not None:
        clauses.append(LeadRow.created_at < end_at)
    return and_(*clauses) if clauses else None


def _normalize_ratio(numerator: int, denominator: int) -> float:
    return round((numerator / denominator), 4) if denominator else 0.0


def _count_metric(key: str, label: str, value: int, unit: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "reason": None,
    }


def _ratio_metric(
    key: str, label: str, numerator: int, denominator: int, no_data_reason: str
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": _normalize_ratio(numerator, denominator) if denominator else None,
        "unit": "ratio",
        "numerator": numerator,
        "denominator": denominator,
        "reason": None if denominator else no_data_reason,
    }


def _money_metric(
    key: str, label: str, value: float | None, no_data_reason: str | None
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": round(value, 6) if value is not None else None,
        "unit": "usd",
        "reason": no_data_reason,
    }


def _sum_agent_cost(payloads: list[dict[str, Any]]) -> float:
    total = 0.0
    for payload in payloads:
        try:
            total += float(payload.get("estimated_cost_usd") or 0)
        except (TypeError, ValueError):
            continue
    return total


@app.get("/v1/admin/launch-readiness")
async def launch_readiness() -> dict[str, Any]:
    """Evaluate first paid-launch gates from docs/research/README.md."""
    try:
        async with get_session() as s:
            funded_buyers = await s.scalar(
                select(func.count(BuyerRow.id)).where(
                    BuyerRow.status == BuyerStatus.ACTIVE.value,
                    BuyerRow.deposit_balance > 0,
                )
            )
            configured_buyers = await s.scalar(
                select(func.count(BuyerRow.id)).where(
                    BuyerRow.status == BuyerStatus.ACTIVE.value,
                    BuyerRow.deposit_balance > 0,
                    func.jsonb_array_length(BuyerRow.target_zips) > 0,
                    func.jsonb_array_length(BuyerRow.services) > 0,
                    BuyerRow.daily_cap > 0,
                    BuyerRow.monthly_budget > 0,
                    BuyerRow.bid_per_lead_t1_t2 > 0,
                    BuyerRow.bid_per_lead_t3 > 0,
                )
            )
            total_wallet_cents = await s.scalar(
                select(func.coalesce(func.sum(BuyerRow.deposit_balance * 100), 0)).where(
                    BuyerRow.status == BuyerStatus.ACTIVE.value
                )
            )
            delivered = await s.scalar(
                select(func.count(PostResult.id)).where(PostResult.delivered.is_(True))
            )
            returned = await s.scalar(
                select(func.count(PostResult.id)).where(PostResult.returned.is_(True))
            )
            attributed_leads = await s.scalar(
                select(func.count(LeadRow.id)).where(
                    LeadRow.campaign_source.is_not(None),
                    LeadRow.campaign_source != "",
                )
            )

        checks = {
            "three_funded_buyers_in_market": int(funded_buyers or 0) >= 3,
            "buyers_have_services_zips_caps_and_prices": int(configured_buyers or 0) >= 3,
            "wallet_balance_present_for_campaign_risk": int(total_wallet_cents or 0) >= 100_000,
            "ping_post_routed_test_lead": int(delivered or 0) > 0,
            "invalid_lead_credit_flow_tested": int(returned or 0) > 0,
            "campaign_source_attribution_visible": int(attributed_leads or 0) > 0,
        }
        ready = all(checks.values())
        return {
            "ready_for_paid_launch": ready,
            "checks": checks,
            "metrics": {
                "funded_buyers": int(funded_buyers or 0),
                "configured_buyers": int(configured_buyers or 0),
                "active_wallet_total_cents": int(total_wallet_cents or 0),
                "delivered_posts": int(delivered or 0),
                "returned_posts": int(returned or 0),
                "attributed_leads": int(attributed_leads or 0),
            },
            "notes": [
                "wallet_balance_present_for_campaign_risk uses a conservative $1,000 seed threshold",
                "expand this endpoint with explicit landing/call-tracking test artifacts as those services ship",
            ],
        }
    except Exception as e:
        log.error("admin.launch_readiness_failed", error=str(e))
        raise HTTPException(
            500, "launch readiness could not be computed; retry after checking database health"
        ) from e


@app.get("/v1/kpis/normalized")
async def normalized_kpis(
    market_state: str | None = Query(default=None, min_length=2, max_length=2),
    market_zip: str | None = Query(default=None, min_length=3, max_length=10),
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    if market_state and market_zip:
        raise HTTPException(400, "choose either market_state or market_zip, not both")
    if start_at and start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=UTC)
    if end_at and end_at.tzinfo is None:
        end_at = end_at.replace(tzinfo=UTC)

    lead_filters = []
    if market_state:
        lead_filters.append(LeadRow.state == market_state.upper())
    if market_zip:
        lead_filters.append(LeadRow.zip == market_zip)
    window_clause = _window_clause(start_at, end_at)
    if window_clause is not None:
        lead_filters.append(window_clause)

    try:
        async with get_session() as s:
            lead_ids_query = select(LeadRow.id)
            if lead_filters:
                lead_ids_query = lead_ids_query.where(and_(*lead_filters))
            lead_ids_subq = lead_ids_query.subquery()

            funded_buyers = await s.scalar(
                select(func.count(BuyerRow.id)).where(BuyerRow.deposit_balance > 0)
            )
            coverage_count = await s.scalar(
                select(func.count(BuyerRow.id)).where(
                    func.jsonb_array_length(BuyerRow.target_zips) > 0
                )
            )
            avg_runway_days = await s.scalar(
                select(
                    func.avg(
                        (BuyerRow.deposit_balance * 30) / func.nullif(BuyerRow.monthly_budget, 0)
                    )
                ).where(BuyerRow.monthly_budget > 0)
            )

            sold_by_class_rows = (
                await s.execute(
                    select(LeadRow.lead_class, func.count(PostResult.id))
                    .join(PostResult, PostResult.lead_id == LeadRow.id)
                    .where(
                        PostResult.delivered.is_(True), LeadRow.id.in_(select(lead_ids_subq.c.id))
                    )
                    .group_by(LeadRow.lead_class)
                )
            ).all()

            return_rate_rows = (
                await s.execute(
                    select(
                        PostResult.buyer_id,
                        LeadRow.campaign_source,
                        func.sum(func.cast(PostResult.returned, Integer)),
                        func.count(PostResult.id),
                    )
                    .join(LeadRow, LeadRow.id == PostResult.lead_id)
                    .where(
                        PostResult.delivered.is_(True), LeadRow.id.in_(select(lead_ids_subq.c.id))
                    )
                    .group_by(PostResult.buyer_id, LeadRow.campaign_source)
                )
            ).all()

            gross_revenue = await s.scalar(
                select(func.coalesce(func.sum(PostResult.bid_cents), 0)).where(
                    PostResult.delivered.is_(True),
                    PostResult.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            credits = await s.scalar(
                select(func.coalesce(func.sum(BillingEvent.amount_cents), 0)).where(
                    BillingEvent.event_type == "lead.returned",
                    BillingEvent.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )

            delivered = await s.scalar(
                select(func.count(PostResult.id)).where(
                    PostResult.delivered.is_(True),
                    PostResult.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            post_errors = await s.scalar(
                select(func.count(PostResult.id)).where(
                    PostResult.delivered.is_(False),
                    PostResult.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            ping_latency_p95 = await s.scalar(
                select(func.percentile_cont(0.95).within_group(PingAttempt.response_ms)).where(
                    PingAttempt.response_ms.is_not(None),
                    PingAttempt.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            ping_avg = await s.scalar(
                select(func.avg(PingAttempt.response_ms)).where(
                    PingAttempt.response_ms.is_not(None),
                    PingAttempt.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            retry_errors = await s.scalar(
                select(func.count(PingAttempt.id)).where(
                    PingAttempt.error.is_not(None),
                    PingAttempt.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            attempts = await s.scalar(
                select(func.count(PingAttempt.id)).where(
                    PingAttempt.lead_id.in_(select(lead_ids_subq.c.id))
                )
            )

        sold_by_class = {str(cls or "unknown"): int(count) for cls, count in sold_by_class_rows}
        return_rate_by_buyer_source = [
            {
                "buyer_id": str(buyer_id),
                "source": source or "unknown",
                "return_rate": _normalize_ratio(int(returns or 0), int(total or 0)),
                "returned": int(returns or 0),
                "sold": int(total or 0),
            }
            for buyer_id, source, returns, total in return_rate_rows
        ]
        net_revenue = int(gross_revenue or 0) - int(credits or 0)
        delivery_success_rate = _normalize_ratio(
            int(delivered or 0), int((delivered or 0) + (post_errors or 0))
        )
        retry_error_rate = _normalize_ratio(int(retry_errors or 0), int(attempts or 0))

        actions = []
        if delivery_success_rate < KPI_THRESHOLDS.pause_delivery_success_rate:
            actions.append("PAUSE")
        if retry_error_rate > KPI_THRESHOLDS.pause_retry_error_rate:
            actions.append("PAUSE")
        if (avg_runway_days or 0) < KPI_THRESHOLDS.pause_wallet_runway_days:
            actions.append("PAUSE")
        if net_revenue < KPI_THRESHOLDS.stop_loss_net_revenue_cents:
            actions.append("STOP_LOSS")

        return {
            "scope": {
                "market_state": market_state.upper() if market_state else None,
                "market_zip": market_zip,
                "start_at": start_at.isoformat() if start_at else None,
                "end_at": end_at.isoformat() if end_at else None,
            },
            "market_readiness": {
                "funded_buyers_count": int(funded_buyers or 0),
                "zip_service_coverage_count": int(coverage_count or 0),
                "wallet_runway_days_avg": float(avg_runway_days or 0),
            },
            "revenue_quality": {
                "sold_leads_by_class": sold_by_class,
                "return_rate_by_buyer_source": return_rate_by_buyer_source,
                "net_revenue_after_credits_cents": net_revenue,
            },
            "ops_health": {
                "delivery_success_rate": delivery_success_rate,
                "ping_latency_ms_avg": float(ping_avg or 0),
                "ping_latency_ms_p95": float(ping_latency_p95 or 0),
                "post_error_rate": _normalize_ratio(
                    int(post_errors or 0), int((delivered or 0) + (post_errors or 0))
                ),
                "retry_error_rate": retry_error_rate,
            },
            "automation": {
                "thresholds": KPI_THRESHOLDS.model_dump(),
                "recommended_actions": sorted(set(actions)),
            },
        }
    except Exception as e:
        log.error("kpi.normalized_failed", error=str(e))
        raise HTTPException(
            500, "normalized kpis could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/kpis/thresholds")
async def get_kpi_thresholds() -> dict[str, Any]:
    return {"thresholds": KPI_THRESHOLDS.model_dump()}


@app.put("/v1/kpis/thresholds")
async def update_kpi_thresholds(payload: KpiThresholdConfig) -> dict[str, Any]:
    global KPI_THRESHOLDS
    KPI_THRESHOLDS = payload
    return {"thresholds": KPI_THRESHOLDS.model_dump()}


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


def _pipeline_state_or_captured(status: str) -> PipelineState:
    try:
        return PipelineState(status)
    except ValueError:
        return PipelineState.CAPTURED


def _lead_admin_summary(lead: LeadRow) -> dict[str, Any]:
    return {
        "status": lead.status,
        "state": lead.state,
        "zip": lead.zip,
        "requested_service": lead.requested_service,
        "damage_tier": lead.damage_tier,
        "lead_class": lead.lead_class,
        "qualification_score": lead.qualification_score,
        "hold_for_review": lead.hold_for_review,
        "blocked_for_fraud": lead.blocked_for_fraud,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }


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
            "low_balance_threshold_cents": _decimal_to_cents(buyer.low_balance_threshold),
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
