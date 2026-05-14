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
import csv
import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import secrets
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from hatchet_sdk import Context, Hatchet
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Integer, and_, func, or_, select, text
from stormlead_core import (
    BuyerSalesStage,
    BuyerStatus,
    Lead,
    PipelineState,
    ProviderArea,
    ProviderDecision,
    configure_logging,
    get_logger,
    provider_decision,
    provider_kill_switch_change_plan,
    provider_live_approved,
    provider_pause_snapshot,
)
from stormlead_db import (
    BillingEvent,
    BudgetActionLog,
    BuyerRow,
    CallEventRow,
    ExceptionQueueItem,
    LeadRow,
    LeadStateTransition,
    LearningProposal,
    PaymentWebhookEvent,
    PingAttempt,
    PostResult,
    ReturnRequest,
    build_transition_idempotency_key,
    get_session,
    latest_state,
    list_lead_timeline,
    list_recent_lead_runs,
    record_transition,
    summarize_transition_payload,
)

from ping_post.attribution import get_campaign_roi, get_roi_by_zip
from ping_post.auction import (
    PING_TIMEOUT_S,
    POST_MAX_ATTEMPTS,
    POST_RETRY_BASE_DELAY_S,
    POST_TIMEOUT_S,
    run_auction,
    validate_buyer_webhook_url,
)
from ping_post.buyer_activation import buyer_activation_readiness
from ping_post.buyer_crm import check_exclusive_zip_conflict
from ping_post.guardrails import evaluate_buyer_guardrails
from ping_post.mailer import export_mailer_csv

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
VALID_RETURN_REVIEW_ACTIONS = {"approve", "hold", "reject"}
ACTIVE_RETURN_REQUEST_STATUSES = ("pending_review", "held")
AUTO_RETURN_APPROVE_REASONS = {"outside_service_area"}
AUTO_RETURN_REJECT_REASONS = {"job_already_completed"}
AUTOPILOT_POLICY_VERSION = "paid-pilot-autopilot-v1"
AUTOPILOT_SUCCESS_STATES = {"sold", "rejected"}
AUTOPILOT_UNSELLABLE_REASONS = {"no_eligible_buyers", "no_accepted_bid"}
EXCEPTION_OWNER_BY_KIND = {
    "return_pending": "support-ops",
    "lead_review": "review-ops",
    "delivery_failure": "ops-oncall",
    "buyer_timeout_cluster": "ops-oncall",
    "no_buyer_coverage": "growth-ops",
    "buyer_wallet_low": "buyer-success",
    "buyer_onboarding_incomplete": "buyer-success",
}
EXCEPTION_SLA_BY_SEVERITY = {
    "critical": timedelta(hours=1),
    "warning": timedelta(hours=24),
    "info": timedelta(hours=72),
}
EXCEPTION_DASHBOARD_AREA_BY_KIND = {
    "return_pending": "support",
    "lead_review": "auction",
    "delivery_failure": "auction",
    "buyer_timeout_cluster": "auction",
    "no_buyer_coverage": "growth",
    "buyer_wallet_low": "finance",
    "buyer_onboarding_incomplete": "growth",
}
ACTIVE_EXCEPTION_QUEUE_STATUSES = {"open", "in_progress"}
ACTIVE_BUDGET_ACTION_STATUSES = {"planned", "approval_required", "blocked"}
ACTIVE_LEARNING_PROPOSAL_STATUSES = {
    "pending_replay",
    "replay_passed",
    "canary_active",
    "rollback_triggered",
    "pending_approval",
}
BUYER_TIMEOUT_CLUSTER_MIN_FAILURES = 3
BUYER_TIMEOUT_CLUSTER_WINDOW = timedelta(hours=1)
PAYMENT_PROVIDERS = {"local", "stripe"}
PAYMENT_CREDITABLE_STATUSES = {"succeeded", "paid"}
PAYMENT_SENSITIVE_METADATA_KEYWORDS = {
    "authorization",
    "card",
    "client_secret",
    "cookie",
    "secret",
    "token",
}
PAYMENT_SENSITIVE_METADATA_VALUE_MARKERS = (
    "bearer ",
    "client_secret=",
    "pi_",
    "secret_",
    "sk_live_",
    "sk_test_",
    "rk_live_",
    "rk_test_",
    "whsec_",
)
STRIPE_SIGNATURE_TOLERANCE_SECONDS = 300
STRIPE_WEBHOOK_MAX_BODY_BYTES = 256 * 1024
STRIPE_SANDBOX_APPROVAL_ENV = "STORMLEAD_APPROVE_PAYMENTS_SANDBOX"


def _payment_error_detail(message: str, error_code: str, **metadata: Any) -> dict[str, Any]:
    detail: dict[str, Any] = {"message": message, "error_code": error_code}
    detail.update({key: value for key, value in metadata.items() if value is not None})
    return detail


def _payment_http_exception(
    status_code: int, message: str, error_code: str, **metadata: Any
) -> HTTPException:
    return HTTPException(status_code, _payment_error_detail(message, error_code, **metadata))


DEFAULT_CANARY_MARKET_STATE = "LA"
DEFAULT_CANARY_SERVICE = "tree_removal"
DEFAULT_CANARY_MONTHLY_BUDGET_CENTS = 10_000
DEFAULT_CANARY_DAILY_BUDGET_CENTS = 333
LOUISIANA_CANARY_ZIPS = {
    "70001",
    "70002",
    "70003",
    "70005",
    "70006",
    "70062",
    "70065",
    "70112",
    "70113",
    "70114",
    "70115",
    "70116",
    "70117",
    "70118",
    "70119",
    "70122",
    "70124",
    "70125",
    "70126",
    "70127",
    "70128",
    "70129",
    "70130",
    "70131",
    "70301",
    "70360",
    "70364",
    "70433",
    "70435",
    "70448",
    "70458",
    "70460",
    "70461",
    "70471",
    "70801",
    "70802",
    "70805",
    "70806",
    "70808",
    "70809",
    "70810",
    "70816",
    "70817",
    "70820",
}
ADS_OFFLINE_CONVERSION_COLUMNS = [
    "Google Click ID",
    "Conversion Name",
    "Conversion Time",
    "Conversion Value",
    "Conversion Currency",
    "Order ID",
]
ADS_DEFAULT_CONVERSION_NAME = "StormLead Sold Lead"
ADS_CLICK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$")
ADS_CONVERSION_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _./()&+'-]{0,127}$")
BUYER_ACTIVATION_FIELDS = frozenset(
    {
        "status",
        "sales_stage",
        "notes",
        "services",
        "target_zips",
        "exclusive_zips",
        "daily_cap",
        "monthly_budget",
        "bid_per_lead_t1_t2",
        "bid_per_lead_t3",
        "bid_per_call",
        "webhook_url",
        "webhook_secret",
        "low_balance_threshold",
    }
)


def _local_buyer_webhook_base() -> str:
    return os.environ.get(
        "STORMLEAD_LOCAL_BUYER_WEBHOOK_BASE",
        "http://host.docker.internal:9999",
    ).rstrip("/")


def _default_buyer_webhook_url(path: str) -> str:
    return f"{_local_buyer_webhook_base()}/{path.lstrip('/')}"


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

    @field_validator("webhook_url")
    @classmethod
    def webhook_url_must_be_local_until_approved(cls, value: str) -> str:
        return validate_buyer_webhook_url(value) or value

    @field_validator("license_state")
    @classmethod
    def license_state_uppercase(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("services", "target_zips", "exclusive_zips")
    @classmethod
    def normalize_string_list(cls, value: list[str]) -> list[str]:
        return _normalize_string_list(value)


class ProviderKillSwitchChangePlanRequest(BaseModel):
    area: ProviderArea
    desired_paused: bool
    reason: str = Field(min_length=3, max_length=500)


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

    @field_validator("webhook_url")
    @classmethod
    def webhook_url_must_be_local_until_approved(cls, value: str | None) -> str | None:
        return validate_buyer_webhook_url(value)

    @field_validator("services", "target_zips", "exclusive_zips")
    @classmethod
    def normalize_optional_string_list(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_string_list(value) if value is not None else None


class DepositRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    external_reference: str | None = Field(default=None, max_length=255)


class WalletRefillIntentRequest(BaseModel):
    amount_cents: int = Field(gt=0, le=5_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    provider: str = Field(default="local", min_length=3, max_length=32)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("provider")
    @classmethod
    def provider_must_be_supported(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in PAYMENT_PROVIDERS:
            allowed = ", ".join(sorted(PAYMENT_PROVIDERS))
            raise ValueError(f"provider must be one of: {allowed}")
        return provider

    @field_validator("currency")
    @classmethod
    def currency_must_be_usd(cls, value: str) -> str:
        currency = value.strip().upper()
        if currency != "USD":
            raise ValueError("currency must be USD for paid-pilot wallet refills")
        return currency


class PaymentRefillEventRequest(BaseModel):
    provider: str = Field(default="local", min_length=3, max_length=32)
    provider_event_id: str = Field(min_length=6, max_length=255)
    payment_intent_id: str = Field(min_length=6, max_length=255)
    buyer_id: UUID
    amount_cents: int = Field(gt=0, le=5_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    status: str = Field(min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider")
    @classmethod
    def event_provider_must_be_supported(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in PAYMENT_PROVIDERS:
            allowed = ", ".join(sorted(PAYMENT_PROVIDERS))
            raise ValueError(f"provider must be one of: {allowed}")
        return provider

    @field_validator("currency")
    @classmethod
    def event_currency_must_be_usd(cls, value: str) -> str:
        currency = value.strip().upper()
        if currency != "USD":
            raise ValueError("currency must be USD for paid-pilot wallet refills")
        return currency

    @field_validator("status")
    @classmethod
    def normalize_event_status(cls, value: str) -> str:
        return value.strip().lower()


class ReturnLeadRequest(BaseModel):
    reason: str = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)
    evidence: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(default="buyer", min_length=1, max_length=128)

    @field_validator("reason")
    @classmethod
    def reason_must_be_valid(cls, value: str) -> str:
        if value not in VALID_RETURN_REASONS:
            allowed = ", ".join(sorted(VALID_RETURN_REASONS))
            raise ValueError(f"reason must be one of: {allowed}")
        return value


class ReturnReviewRequest(BaseModel):
    action: str = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)
    operator: str = Field(default="local-admin", min_length=1, max_length=128)

    @field_validator("action")
    @classmethod
    def action_must_be_valid(cls, value: str) -> str:
        action = value.strip().lower()
        if action not in VALID_RETURN_REVIEW_ACTIONS:
            allowed = ", ".join(sorted(VALID_RETURN_REVIEW_ACTIONS))
            raise ValueError(f"action must be one of: {allowed}")
        return action


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


hatchet = Hatchet()
_supports_legacy_hatchet_worker = hasattr(hatchet, "step")
_legacy_hatchet = cast(Any, hatchet)


class _ContextAdapter:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.workflow_input = payload


def _task_payload(task_input: Any, context: Context) -> dict[str, Any]:
    if isinstance(task_input, dict):
        return task_input
    model_dump = getattr(task_input, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict) and dumped:
            return dumped
    workflow_input = getattr(context, "workflow_input", None)
    payload = workflow_input() if callable(workflow_input) else workflow_input
    return payload if isinstance(payload, dict) else {}


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


async def _latest_delivered_post_for_lead(lead_id: UUID) -> PostResult | None:
    async with get_session() as s:
        return (
            (
                await s.execute(
                    select(PostResult)
                    .where(PostResult.lead_id == lead_id, PostResult.delivered.is_(True))
                    .order_by(PostResult.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )


if _supports_legacy_hatchet_worker:

    @_legacy_hatchet.workflow(name="ping-post-auction", on_events=["lead.qualified"])
    class PingPostWorkflow:
        """Hatchet SDK v0.x workflow wrapper."""

        @_legacy_hatchet.step(timeout=timedelta(seconds=30), retries=3)
        async def auction(self, context: Context) -> dict[str, Any]:
            return await _auction_step(context)

    @_legacy_hatchet.workflow(name="GuardrailEvaluation", on_crons=["0 6 * * *"])
    class GuardrailEvaluation:
        @_legacy_hatchet.step(timeout=timedelta(seconds=300), retries=1)
        async def evaluate(self, context: Context) -> dict[str, Any]:
            return {"actions": await evaluate_buyer_guardrails()}

else:

    @hatchet.task(
        name="ping-post-auction",
        on_events=["lead.qualified"],
        execution_timeout=timedelta(seconds=30),
        retries=3,
    )
    async def ping_post_auction_task(task_input: Any, context: Context) -> dict[str, Any]:
        adapted = _ContextAdapter(_task_payload(task_input, context))
        return await _auction_step(cast(Context, adapted))

    @hatchet.task(
        name="GuardrailEvaluation",
        on_crons=["0 6 * * *"],
        execution_timeout=timedelta(seconds=300),
        retries=1,
    )
    async def guardrail_evaluation_task(task_input: Any, context: Context) -> dict[str, Any]:
        return {"actions": await evaluate_buyer_guardrails()}


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
        damage_type=row.damage_type,
        urgency=row.urgency,
        damage_summary=row.damage_summary,
        visible_risk_level=row.visible_risk_level,
        estimated_job_size=row.estimated_job_size,
        buyer_notes=row.buyer_notes,
        damage_tier=DamageTier(row.damage_tier) if row.damage_tier else None,
        photo_s3_keys=row.photo_s3_keys or [],
        safety_flags=row.safety_flags or [],
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
        score=row.score,
        score_reason=row.score_reason,
        hold_for_review=row.hold_for_review,
        blocked_for_fraud=row.blocked_for_fraud,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task: asyncio.Task | None = None
    if _supports_legacy_hatchet_worker:
        worker = _legacy_hatchet.worker("ping-post-worker", max_runs=10)
        worker.register_workflow(PingPostWorkflow())
        worker.register_workflow(GuardrailEvaluation())
    else:
        worker = hatchet.worker(
            "ping-post-worker",
            slots=10,
            workflows=[ping_post_auction_task, guardrail_evaluation_task],
        )
    async_start = getattr(worker, "async_start", None)
    if callable(async_start):
        task = asyncio.create_task(_start_hatchet_worker_async(async_start))
    else:
        task = asyncio.create_task(asyncio.to_thread(_start_hatchet_worker_sync, worker))
    log.info("startup.complete")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
        log.info("shutdown.complete")


async def _start_hatchet_worker_async(async_start: Any) -> None:
    try:
        await async_start()
    except asyncio.CancelledError:
        raise
    except BaseException as e:
        log.error("hatchet.worker_start_failed", error=str(e))


def _start_hatchet_worker_sync(worker: Any) -> None:
    try:
        worker.start()
    except BaseException as e:
        log.error("hatchet.worker_start_failed", error=str(e))


app = FastAPI(title="stormlead ping-post", lifespan=lifespan)


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _request_ip(request: Request) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_local_dev_request(request: Request) -> bool:
    ip = _request_ip(request)
    if ip is None:
        return False
    if ip.is_loopback:
        return True
    return _truthy_env("STORMLEAD_LOCAL_AUTH_BYPASS") and (ip.is_private or ip.is_link_local)


def _authorization_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def _buyer_api_key_matches(request: Request, buyer: BuyerRow) -> bool:
    supplied = _authorization_bearer_token(request)
    return bool(buyer.api_key and supplied and hmac.compare_digest(str(buyer.api_key), supplied))


def _operator_token(request: Request) -> str | None:
    header_token = request.headers.get("x-stormlead-operator-token", "").strip()
    return header_token or _authorization_bearer_token(request)


def _operator_path_requires_gate(path: str, method: str) -> bool:
    if path == "/v1/payments/stripe/refill-webhook":
        return False
    if path.startswith("/v1/admin/"):
        return True
    if path.startswith("/v1/kpis/"):
        return True
    if path == "/v1/auction":
        return True
    if path == "/v1/buyers":
        return True
    if path.startswith("/v1/return-requests/") and path.endswith("/review"):
        return True
    if path.startswith("/v1/payments/"):
        return True
    if path.startswith("/v1/buyers/") and method in {"PATCH", "DELETE"}:
        return True
    if path.startswith("/v1/buyers/") and path.endswith("/wallet/refill-intents"):
        return True
    return path.startswith("/v1/buyers/") and path.endswith("/deposits")


def _operator_authorized(request: Request) -> bool:
    if not _truthy_env("STORMLEAD_REQUIRE_OPERATOR_TOKEN") and _is_local_dev_request(request):
        return True
    expected = os.getenv("STORMLEAD_OPERATOR_TOKEN", "").strip()
    supplied = _operator_token(request)
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


@app.middleware("http")
async def operator_surface_gate(request: Request, call_next: Any) -> Response:
    if _operator_path_requires_gate(request.url.path, request.method) and not _operator_authorized(
        request
    ):
        return JSONResponse(
            {"detail": "operator token required for admin or funding operations"},
            status_code=401,
        )
    return await call_next(request)


def _buyer_api_key_required(request: Request) -> bool:
    return _truthy_env("STORMLEAD_REQUIRE_BUYER_API_KEY") or not _is_local_dev_request(request)


def _require_buyer_api_key(request: Request, buyer: BuyerRow) -> None:
    if not _buyer_api_key_required(request):
        return
    if _buyer_api_key_matches(request, buyer):
        return
    if _operator_token_supplied_and_authorized(request):
        return
    raise HTTPException(401, "valid buyer API key required")


def _operator_token_supplied_and_authorized(request: Request) -> bool:
    expected = os.getenv("STORMLEAD_OPERATOR_TOKEN", "").strip()
    supplied = _operator_token(request)
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _new_buyer_api_key() -> str:
    return f"buyer_{secrets.token_urlsafe(32)}"


@app.get("/admin", response_class=HTMLResponse)
async def admin() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="StormLead local admin dashboard for synthetic lead workflow proof, buyer wallet controls, return review, and launch-readiness checks." />
  <title>StormLead Admin</title>
  <style>
    :root { color-scheme: dark; --bg: #030303; --glass: rgba(10, 10, 10, .7); --glass-strong: rgba(8, 8, 8, .82); --border: rgba(255, 255, 255, .1); --border-soft: rgba(255, 255, 255, .05); --muted: #a3a3a3; --text: #fff; --accent: #06b6d4; --accent-2: #10b981; --violet: #8b5cf6; --warn: #f59e0b; --danger: #fb7185; --ease: cubic-bezier(.23, 1, .32, 1); }
    * { box-sizing: border-box; }
    html { background: var(--bg); scroll-behavior: smooth; }
    body { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; min-height: 100vh; overflow-x: hidden; background: radial-gradient(circle at top center, rgba(139, 92, 246, .4), transparent 34rem), radial-gradient(circle at left center, rgba(6, 182, 212, .08), transparent 42rem), #030303; color: var(--text); }
    body::before { background-image: linear-gradient(rgba(255,255,255,.032) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.032) 1px, transparent 1px); background-size: 72px 72px; content: ""; inset: 0; mask-image: linear-gradient(to bottom, rgba(0,0,0,.72), transparent 78%); pointer-events: none; position: fixed; }
    @keyframes float-orb { from { transform: translateY(0) scale(1); } to { transform: translateY(-20px) scale(1.05); } }
    @keyframes shimmer { from { background-position: 200% center; } to { background-position: -200% center; } }
    @keyframes spin { to { transform: rotate(1turn); } }
    @keyframes marquee { to { transform: translateX(-50%); } }
    @keyframes enter { to { opacity: 1; transform: translateY(0); } }
    @keyframes pulse { 50% { opacity: .35; transform: scale(.72); } }
    .orb { border-radius: 999px; filter: blur(90px); opacity: .78; pointer-events: none; position: fixed; z-index: 0; animation: float-orb 12s var(--ease) infinite alternate; }
    .orb.violet { background: rgba(139, 92, 246, .4); height: 18rem; right: 7vw; top: 11vh; width: 18rem; }
    .orb.cyan { animation-duration: 15s; background: rgba(6, 182, 212, .4); bottom: 13vh; height: 15rem; left: 5vw; width: 15rem; }
    h1, h2 { font-family: "Instrument Serif", Georgia, serif; font-weight: 400; letter-spacing: -.045em; margin: 0; }
    h1 { font-size: clamp(3.6rem, 8vw, 7.2rem); line-height: .88; max-width: 920px; }
    h2 { font-size: clamp(1.7rem, 3vw, 2.45rem); line-height: .96; }
    p { color: var(--muted); font-weight: 300; line-height: 1.65; }
    .admin-shell { margin: 0 auto; padding: 7.5rem 1rem 4rem; position: relative; width: min(1480px, 100%); z-index: 1; }
    .nav-pill { align-items: center; backdrop-filter: blur(16px); background: var(--glass); border: 1px solid var(--border); border-radius: 999px; display: grid; gap: .75rem; grid-template-columns: 1fr auto 1fr; left: 50%; max-width: 672px; padding: .55rem .65rem; position: fixed; top: 1.5rem; transform: translateX(-50%); width: 95%; z-index: 10; }
    .brand { align-items: center; color: #fff; display: inline-flex; font-family: "Instrument Serif", Georgia, serif; font-size: 1.2rem; gap: .5rem; letter-spacing: -.02em; text-decoration: none; white-space: nowrap; }
    .brand-dot { background: linear-gradient(135deg, var(--violet), var(--accent)); border-radius: 999px; box-shadow: 0 0 20px -6px var(--violet); height: .45rem; width: .45rem; }
    .nav-links { display: flex; gap: .85rem; justify-content: center; }
    .nav-links a { color: #a3a3a3; font-size: .72rem; font-weight: 600; letter-spacing: .18em; text-decoration: none; text-transform: uppercase; transition: color .7s var(--ease); }
    .nav-links a:hover { color: #fff; }
    .nav-cta { background: #fff; border-radius: 999px; color: #000; font-size: .78rem; font-weight: 700; justify-self: end; padding: .62rem .95rem; text-decoration: none; }
    .hero { backdrop-filter: blur(16px); border: 1px solid var(--border); border-radius: 1.5rem; padding: clamp(1.6rem, 4vw, 3rem); background: rgba(8, 8, 8, .8); box-shadow: 0 0 20px -10px rgba(139,92,246,.4); overflow: hidden; position: relative; }
    .hero::before { background: radial-gradient(circle, rgba(139,92,246,.28), transparent 48%); content: ""; filter: blur(44px); height: 18rem; position: absolute; right: -4rem; top: -6rem; width: 18rem; }
    .hero::after { background: linear-gradient(90deg, rgba(139,92,246,.85), rgba(6,182,212,.75), transparent); bottom: 0; content: ""; height: 1px; left: 0; position: absolute; right: 0; }
    .hero-top, .section-header, .toolbar { align-items: center; display: flex; flex-wrap: wrap; gap: .75rem; justify-content: space-between; }
    .eyebrow { color: #737373; font-size: .62rem; font-weight: 600; letter-spacing: .2em; text-transform: uppercase; }
    .subtitle { color: var(--muted); font-size: 1.05rem; max-width: 760px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1rem; margin: 1rem 0 1.5rem; }
    .two-column { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(320px, .9fr); gap: 1rem; }
    .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: .85rem; }
    .card, table, form, .panel { backdrop-filter: blur(16px); background: rgba(255, 255, 255, .02); border: 1px solid var(--border-soft); border-radius: 1.5rem; box-shadow: 0 0 20px -14px #8b5cf6; }
    .card { min-height: 112px; opacity: 0; overflow: hidden; padding: 1.35rem; position: relative; transform: translateY(20px); animation: enter .9s var(--ease) forwards; transition: transform .9s var(--ease), border-color .9s var(--ease), background .9s var(--ease), box-shadow .9s var(--ease); }
    .card::after { background: linear-gradient(90deg, var(--violet), var(--accent), transparent); bottom: 0; content: ""; height: 1px; left: 0; position: absolute; right: 0; }
    .card:hover { background: rgba(255,255,255,.045); border-color: rgba(139,92,246,.4); box-shadow: 0 0 20px -10px rgba(139,92,246,.4); transform: translateY(-12px); }
    .metric { color: #fff; font-size: clamp(1.65rem, 4vw, 2.25rem); font-weight: 600; letter-spacing: -.03em; margin-top: .35rem; }
    form, .panel { margin: 1rem 0; padding: 1.2rem; }
    label { display: grid; gap: .45rem; color: #d4d4d4; font-size: .72rem; font-weight: 600; letter-spacing: .13em; text-transform: uppercase; }
    input, select, textarea { background: rgba(3,3,3,.88); border: 1px solid var(--border); border-radius: 1rem; color: var(--text); min-height: 2.9rem; padding: .76rem .86rem; transition: border-color .7s var(--ease), box-shadow .7s var(--ease); width: 100%; }
    input:focus, select:focus, textarea:focus { border-color: rgba(6,182,212,.72); box-shadow: 0 0 0 4px rgba(6,182,212,.12); outline: none; }
    textarea { min-height: 4.75rem; resize: vertical; }
    button { background: #fff; border: 0; border-radius: 999px; color: #000; cursor: pointer; font-weight: 700; min-height: 2.9rem; padding: .8rem 1.2rem; transition: transform .7s var(--ease), filter .7s var(--ease); }
    button.secondary { background: rgba(255,255,255,.06); border: 1px solid var(--border); color: #fff; }
    button.ghost { background: rgba(10,10,10,.7); border: 1px solid var(--border); color: #fff; }
    button:hover { filter: brightness(.95); transform: translateY(-2px); }
    button:disabled { cursor: wait; filter: grayscale(.4); opacity: .7; transform: none; }
    .actions { display: flex; flex-wrap: wrap; gap: .75rem; margin-top: 1rem; }
    .status { backdrop-filter: blur(16px); background: rgba(10,10,10,.7); border: 1px solid var(--border); border-left: 5px solid var(--accent); border-radius: 1.1rem; margin: 1rem 0; padding: .9rem 1rem; white-space: pre-wrap; }
    .status.ok { border-left-color: var(--accent-2); }
    .status.error { border-left-color: var(--danger); }
    .muted { color: var(--muted); }
    .mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .84rem; }
    .pill { align-items: center; background: rgba(10,10,10,.7); border: 1px solid var(--border); border-radius: 999px; color: #d4d4d4; display: inline-flex; font-size: .7rem; font-weight: 600; gap: .35rem; letter-spacing: .16em; padding: .4rem .75rem; text-transform: uppercase; }
    .pill.ok { border-color: rgba(16,185,129,.45); color: #6ee7b7; }
    .pill.warn { border-color: rgba(245,158,11,.45); color: #fde68a; }
    .pill.danger { border-color: rgba(251,113,133,.45); color: #fecdd3; }
    .shimmer { animation: shimmer 5s linear infinite; background: linear-gradient(90deg, #a78bfa 0%, #fff 40%, #fff 60%, #22d3ee 100%); background-clip: text; background-size: 200%; color: transparent; }
    .ticker { border-bottom: 1px solid var(--border-soft); border-top: 1px solid var(--border-soft); background: rgba(0,0,0,.4); height: 60px; margin: 1rem calc(50% - 50vw); overflow: hidden; }
    .ticker-track { align-items: center; animation: marquee 40s linear infinite; display: flex; gap: 2.5rem; height: 100%; min-width: max-content; width: max-content; }
    .ticker-item { align-items: baseline; display: inline-flex; gap: .65rem; white-space: nowrap; }
    .ticker-label { color: #737373; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .62rem; letter-spacing: .2em; text-transform: uppercase; }
    .ticker-value { color: #fff; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 1rem; }
    .accent-violet { color: #a78bfa; } .accent-cyan { color: #22d3ee; } .accent-emerald { color: #34d399; }
    .readiness-grid { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-top: .9rem; }
    .check-list { display: grid; gap: .45rem; margin-top: .9rem; }
    .check-row { align-items: center; display: flex; gap: .5rem; justify-content: space-between; }
    .timeline { display: grid; gap: .75rem; margin-top: 1rem; }
    .timeline-event { background: rgba(8,8,8,.8); border: 1px solid var(--border-soft); border-left: 4px solid var(--accent); border-radius: 1.1rem; padding: .9rem; }
    .timeline-event.review { border-left-color: #facc15; }
    .timeline-event.attention { border-left-color: var(--danger); }
    .payload { background: rgba(3,3,3,.88); border: 1px solid var(--border-soft); border-radius: 1rem; color: #d4d4d4; overflow: auto; padding: .75rem; }
    .table-wrap { border: 1px solid var(--border-soft); border-radius: 1.5rem; overflow-x: auto; }
    table { border: 0; border-collapse: collapse; min-width: 780px; width: 100%; }
    th, td { padding: 0.78rem; border-bottom: 1px solid var(--border-soft); text-align: left; vertical-align: top; }
    th { background: rgba(8,8,8,.82); color: #737373; font-size: .62rem; font-weight: 600; letter-spacing: .2em; position: sticky; text-transform: uppercase; top: 0; }
    tr[data-lead-id], tr[data-buyer-id] { cursor: pointer; }
    tr[data-lead-id]:hover, tr[data-buyer-id]:hover { background: rgba(139,92,246,.1); }
    @media (max-width: 900px) { .nav-pill { grid-template-columns: 1fr auto; } .nav-links { display: none; } .two-column { grid-template-columns: 1fr; } .hero { border-radius: 20px; } }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .001ms !important; animation-iteration-count: 1 !important; scroll-behavior: auto !important; transition-duration: .001ms !important; } }
  </style>
</head>
<body>
  <div class="orb violet"></div>
  <div class="orb cyan"></div>
  <nav class="nav-pill" aria-label="primary navigation">
    <a class="brand" href="/admin"><span class="brand-dot"></span><span>StormLead</span></a>
    <div class="nav-links"><a href="#kpis">Metrics</a><a href="#autopilot">Autopilot</a><a href="#workflow-runs">Runs</a><a href="#buyers">Buyers</a></div>
    <a class="nav-cta" href="#buyer-form">Create</a>
  </nav>
  <main class="admin-shell">
    <section class="hero">
      <div class="hero-top">
        <span class="eyebrow">Local simulation operations</span>
        <div class="toolbar">
          <span class="pill ok">Synthetic data only</span>
          <span class="pill danger">Commercial launch locked</span>
          <button type="button" class="ghost" onclick="load()">Refresh Dashboard</button>
        </div>
      </div>
      <h1>StormLead <span class="shimmer">Admin</span></h1>
      <p class="subtitle">Paid-pilot control surface for proving the local lead workflow, buyer wallet controls, returns, and audit timeline without contacting real homeowners or buyers.</p>
    </section>

    <section class="ticker" aria-label="local operating status">
      <div class="ticker-track">
        <div class="ticker-item"><span class="ticker-label">Mode</span><span class="ticker-value accent-violet">Synthetic Local</span></div>
        <div class="ticker-item"><span class="ticker-label">LLM</span><span class="ticker-value accent-cyan">LiteLLM Routed</span></div>
        <div class="ticker-item"><span class="ticker-label">Launch</span><span class="ticker-value accent-emerald">Locked Safe</span></div>
        <div class="ticker-item"><span class="ticker-label">Evidence</span><span class="ticker-value">Audited</span></div>
        <div class="ticker-item"><span class="ticker-label">Buyers</span><span class="ticker-value">Wallet Gated</span></div>
        <div class="ticker-item"><span class="ticker-label">Mode</span><span class="ticker-value accent-violet">Synthetic Local</span></div>
        <div class="ticker-item"><span class="ticker-label">LLM</span><span class="ticker-value accent-cyan">LiteLLM Routed</span></div>
        <div class="ticker-item"><span class="ticker-label">Launch</span><span class="ticker-value accent-emerald">Locked Safe</span></div>
        <div class="ticker-item"><span class="ticker-label">Evidence</span><span class="ticker-value">Audited</span></div>
        <div class="ticker-item"><span class="ticker-label">Buyers</span><span class="ticker-value">Wallet Gated</span></div>
      </div>
    </section>

    <section class="grid" id="kpis" aria-label="business kpis"></section>

    <section class="panel" id="autopilot" aria-label="paid pilot autopilot">
      <div class="section-header">
        <div>
          <h2>99% Autopilot</h2>
          <p class="muted">Straight-through paid-pilot processing: normal synthetic leads sell, reject, or route automatically; only exceptions stay here for operator review.</p>
        </div>
        <span class="pill" id="autopilot-label">loading</span>
      </div>
      <section class="grid" id="autopilot-kpis" aria-label="autopilot kpis"></section>
      <div class="section-header">
        <div>
          <h2>Durable Queue Summary</h2>
          <p class="muted">Read-only `exception_queue` rollup by owner, SLA, severity, and operations area. Aggregates only; no homeowner PII.</p>
        </div>
        <span class="pill" id="exception-summary-label">loading</span>
      </div>
      <section class="grid" id="exception-summary" aria-label="durable exception queue summary"></section>
      <div class="section-header">
        <div>
          <h2>Budget Action Queue</h2>
          <p class="muted">Read-only `budget_action_logs` view for pause recommendations, blocked cap breaches, and approval-required budget increases. No ad platform mutation or spend.</p>
        </div>
        <span class="pill" id="budget-actions-label">loading</span>
      </div>
      <section class="grid" id="budget-actions-summary" aria-label="budget action summary"></section>
      <div class="table-wrap">
        <table aria-label="budget action approval queue">
          <thead><tr><th>Action</th><th>Status</th><th>Platform</th><th>Campaign</th><th>Reason</th><th>Safety</th></tr></thead>
          <tbody id="budget-actions"></tbody>
        </table>
      </div>
      <div class="section-header">
        <div>
          <h2>Learning Proposal Queue</h2>
          <p class="muted">Read-only `learning_proposals` view for replay guardrails, 5% canaries, rollbacks, and approval-required promotions. No live traffic routing or automatic promotion.</p>
        </div>
        <span class="pill" id="learning-proposals-label">loading</span>
      </div>
      <section class="grid" id="learning-proposals-summary" aria-label="learning proposal summary"></section>
      <div class="table-wrap">
        <table aria-label="learning proposal replay queue">
          <thead><tr><th>Type</th><th>Status</th><th>Target</th><th>Canary</th><th>Guardrail</th><th>Safety</th></tr></thead>
          <tbody id="learning-proposals"></tbody>
        </table>
      </div>
      <div class="section-header">
        <div>
          <h2>Exception Queue</h2>
          <p class="muted">Derived from local audit rows, return requests, delivery results, and buyer wallet readiness. List view avoids homeowner PII.</p>
        </div>
        <button type="button" class="secondary" onclick="loadAutopilot()">Refresh Exceptions</button>
      </div>
      <div class="table-wrap">
        <table aria-label="autopilot exception queue">
          <thead><tr><th>Severity</th><th>Reason</th><th>Context</th><th>Age</th><th>Recommended Action</th><th>Actions</th></tr></thead>
          <tbody id="exception-queue"></tbody>
        </table>
      </div>
    </section>

    <section class="panel" aria-label="launch readiness">
      <div class="section-header">
        <div>
          <h2>Launch Readiness</h2>
          <p class="muted">Separates local simulation readiness from technical paid-pilot gates and commercial approval.</p>
        </div>
        <span class="pill" id="readiness-label">loading</span>
      </div>
      <div id="readiness"></div>
    </section>

    <section class="panel" aria-label="cowork workflow controls">
      <div class="section-header">
        <div>
          <h2>Cowork Workflow Controls</h2>
          <p>Create a real buyer, activate/fund it, then verify dashboard KPIs and roster state.</p>
        </div>
      </div>
      <div class="status" id="workflow-status" role="status" aria-live="polite">Ready. No mock data is used.</div>
    </section>

    <div class="two-column">
      <section>
        <div class="section-header"><h2>Agentic Workflow KPIs</h2></div>
        <section class="grid" id="workflow-kpis"></section>

        <section class="panel" aria-label="workflow timeline">
          <h2>Lead Workflow Timeline</h2>
          <p class="muted">Inspect append-only state transitions, agent decisions, review actions, and redacted payload summaries from real database audit rows.</p>
          <form id="timeline-form" aria-label="load lead timeline form">
            <div class="form-grid">
              <label>Lead ID <input name="lead_id" id="timeline-lead-id" placeholder="Paste a lead UUID" aria-describedby="timeline-summary" aria-invalid="false" inputmode="text" /></label>
              <label>Review Notes <input name="notes" id="review-notes" value="Reviewed in StormLead admin timeline." /></label>
            </div>
            <div class="actions">
              <button type="submit">Load Timeline</button>
              <button type="button" class="secondary" id="review-hold">Hold For Review</button>
              <button type="button" class="secondary" id="review-approve">Approve / Clear Hold</button>
            </div>
          </form>
          <div id="timeline-summary" class="status" role="status" aria-live="polite">Select a lead from Recent Workflow Runs or paste a lead UUID.</div>
          <div class="timeline" id="timeline"></div>
        </section>
      </section>

      <section>
        <section class="panel" aria-label="recent workflow runs">
          <h2>Recent Workflow Runs</h2>
          <p class="muted">Rows are grouped from lead_state_transitions and can be opened in the timeline.</p>
          <div class="table-wrap">
            <table aria-label="workflow runs">
              <thead><tr><th>Updated</th><th>State</th><th>Status</th><th>Events</th><th>Latest Event</th><th>Lead ID</th></tr></thead>
              <tbody id="workflow-runs"></tbody>
            </table>
          </div>
        </section>
      </section>
    </div>

    <form id="buyer-form" aria-label="create buyer form">
      <div class="section-header"><h2>Create Buyer</h2><span class="pill">Step 1</span></div>
      <div class="form-grid">
        <label>Name <input name="name" value="Cowork Buyer" required /></label>
        <label>Company <input name="company" value="Cowork Tree Pros" required /></label>
        <label>Email <input name="contact_email" value="ops@cowork-tree.example" required /></label>
        <label>Phone <input name="contact_phone_e164" value="+15125550199" required /></label>
        <label>Webhook URL <input name="webhook_url" value="__DEFAULT_BUYER_WEBHOOK_URL__" required /></label>
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

    <div class="two-column">
      <form id="buyer-update-form" aria-label="update buyer form">
        <div class="section-header"><h2>Activate / Fund Buyer</h2><span class="pill">Step 2</span></div>
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
        <div class="section-header"><h2>Add Deposit</h2><span class="pill">Step 3</span></div>
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
    </div>

    <section class="panel" aria-label="buyer roster">
      <div class="section-header"><h2>Buyers</h2><span class="pill" id="buyer-count">loading</span></div>
      <div class="table-wrap">
        <table aria-label="buyers">
          <thead><tr><th>Company</th><th>Status</th><th>Stage</th><th>Wallet</th><th>Services</th><th>Zips</th><th>Low Balance</th><th>ID</th></tr></thead>
          <tbody id="buyers"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const money = cents => `$${(cents / 100).toFixed(2)}`;
    const statusBox = document.querySelector('#workflow-status');
    const setStatus = (msg, kind = '') => {
      statusBox.textContent = msg;
      statusBox.className = ['status', kind].filter(Boolean).join(' ');
    };
    const htmlEscapeMap = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => htmlEscapeMap[ch]);
    const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    const list = value => value.split(',').map(v => v.trim()).filter(Boolean);
    const formJson = form => Object.fromEntries(new FormData(form).entries());
    const setTimelineMessage = (msg, kind = '') => {
      const summary = document.querySelector('#timeline-summary');
      const input = document.querySelector('#timeline-lead-id');
      summary.textContent = msg;
      summary.className = ['status', kind].filter(Boolean).join(' ');
      summary.setAttribute('role', kind === 'error' ? 'alert' : 'status');
      summary.setAttribute('aria-live', kind === 'error' ? 'assertive' : 'polite');
      input.setAttribute('aria-invalid', kind === 'error' ? 'true' : 'false');
    };
    const validateLeadId = leadId => {
      if (!leadId) return 'Paste or select a lead UUID before loading the timeline.';
      if (!uuidPattern.test(leadId)) return 'Lead ID must be a valid UUID before StormLead can load the audit timeline.';
      return '';
    };
    const operatorHeaders = () => {
      const token = window.localStorage.getItem('stormlead_operator_token') || '';
      return token ? { Authorization: `Bearer ${token}` } : {};
    };
    const api = async (path, options = {}) => {
      const res = await fetch(path, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...operatorHeaders(), ...(options.headers || {}) },
      });
      const text = await res.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { detail: text };
      }
      if (res.status === 401) {
        const token = window.prompt('Operator token required for protected admin operations.');
        if (token) {
          window.localStorage.setItem('stormlead_operator_token', token);
          return api(path, options);
        }
      }
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

    const titleize = value => String(value || '').replaceAll('_', ' ');
    const readinessClass = data => data.commercial_paid_launch_ready ? 'ok' : data.local_simulation_ready ? 'warn' : 'danger';

    function renderReadiness(data) {
      const label = document.querySelector('#readiness-label');
      label.textContent = titleize(data.readiness_label);
      label.className = `pill ${readinessClass(data)}`;
      const metrics = data.metrics || {};
      const checks = Object.entries(data.checks || {}).map(([name, passed]) => `
        <div class="check-row">
          <span>${escapeHtml(titleize(name))}</span>
          <span class="pill ${passed ? 'ok' : 'danger'}">${passed ? 'pass' : 'blocked'}</span>
        </div>`).join('');
      document.querySelector('#readiness').innerHTML = `
        <div class="readiness-grid">
          <div class="card"><div>Funded Buyers</div><div class="metric">${escapeHtml(metrics.funded_buyers ?? 0)}</div><div class="muted">Need 3 for technical local readiness</div></div>
          <div class="card"><div>Wallet Coverage</div><div class="metric">${money(metrics.active_wallet_total_cents || 0)}</div><div class="muted">Against ${money((data.scope || {}).campaign_budget_cents || 0)} test budget</div></div>
          <div class="card"><div>Runway Buyers</div><div class="metric">${escapeHtml(metrics.runway_ready_buyers ?? 0)}</div><div class="muted">Need 3 above ${escapeHtml(metrics.required_runway_days ?? 0)} days</div></div>
          <div class="card"><div>Routed Posts</div><div class="metric">${escapeHtml(metrics.delivered_posts ?? 0)}</div><div class="muted">Synthetic ping/post evidence</div></div>
          <div class="card"><div>Approved Returns</div><div class="metric">${escapeHtml(metrics.approved_return_requests ?? 0)}</div><div class="muted">Credit review evidence</div></div>
        </div>
        <div class="check-list">${checks || '<div class="muted">No readiness checks returned.</div>'}</div>`;
    }

    function renderWorkflowKpis(data) {
      const metrics = data.metrics || [];
      document.querySelector('#workflow-kpis').innerHTML = metrics.length ? metrics.map(metric => `
        <div class="card">
          <div>${escapeHtml(metric.label)}</div>
          <div class="metric">${escapeHtml(metricValue(metric))}</div>
          <div class="muted">${escapeHtml(metricDetail(metric))}</div>
        </div>`).join('') : '<div class="muted">No workflow KPIs are available yet.</div>';
    }

    function renderAutopilotKpis(data) {
      const label = document.querySelector('#autopilot-label');
      const score = Number(data.straight_through_rate || 0);
      label.textContent = `${(score * 100).toFixed(1)}% STP`;
      label.className = `pill ${score >= 0.99 ? 'ok' : score >= 0.9 ? 'warn' : 'danger'}`;
      const metrics = data.metrics || [];
      document.querySelector('#autopilot-kpis').innerHTML = metrics.length ? metrics.map(metric => `
        <div class="card">
          <div>${escapeHtml(metric.label)}</div>
          <div class="metric">${escapeHtml(metricValue(metric))}</div>
          <div class="muted">${escapeHtml(metricDetail(metric))}</div>
        </div>`).join('') : '<div class="muted">No autopilot KPI data is available yet.</div>';
    }

    function compactCounts(counts) {
      const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      if (!entries.length) return 'none';
      return entries.map(([key, value]) => `${titleize(key)}: ${value}`).join(' | ');
    }

    function renderExceptionSummary(data) {
      const label = document.querySelector('#exception-summary-label');
      const active = Number(data.active_count || 0);
      const overdue = Number(data.overdue_count || 0);
      label.textContent = `${active} active`;
      label.className = `pill ${overdue ? 'danger' : active ? 'warn' : 'ok'}`;
      document.querySelector('#exception-summary').innerHTML = `
        <div class="card"><div>Active Durable Exceptions</div><div class="metric">${escapeHtml(active)}</div><div class="muted">Open or in-progress queue rows</div></div>
        <div class="card"><div>SLA Overdue</div><div class="metric">${escapeHtml(overdue)}</div><div class="muted">Oldest due: ${escapeHtml(data.oldest_sla_due_at || 'none')}</div></div>
        <div class="card"><div>Operations Areas</div><div class="metric">${escapeHtml(Object.keys(data.by_area || {}).length)}</div><div class="muted">${escapeHtml(compactCounts(data.by_area))}</div></div>
        <div class="card"><div>Owners</div><div class="metric">${escapeHtml(Object.keys(data.by_owner || {}).length)}</div><div class="muted">${escapeHtml(compactCounts(data.by_owner))}</div></div>
        <div class="card"><div>Severity Mix</div><div class="metric">${escapeHtml(Object.keys(data.by_severity || {}).length)}</div><div class="muted">${escapeHtml(compactCounts(data.by_severity))}</div></div>`;
    }

    function renderBudgetActions(data) {
      const label = document.querySelector('#budget-actions-label');
      const active = Number(data.active_count || 0);
      const approvals = Number(data.approval_required_count || 0);
      const unsafeIntent = Number(data.rows_with_provider_contact_intent || 0) + Number(data.rows_with_provider_mutation_intent || 0) + Number(data.rows_with_spend_intent || 0);
      label.textContent = `${approvals} approvals`;
      label.className = `pill ${unsafeIntent || Number(data.blocked_count || 0) ? 'danger' : active ? 'warn' : 'ok'}`;
      document.querySelector('#budget-actions-summary').innerHTML = `
        <div class="card"><div>Active Budget Actions</div><div class="metric">${escapeHtml(active)}</div><div class="muted">Read-only local audit rows</div></div>
        <div class="card"><div>Approval Required</div><div class="metric">${escapeHtml(approvals)}</div><div class="muted">Budget increases stay manual</div></div>
        <div class="card"><div>Auto-Pause Plans</div><div class="metric">${escapeHtml(data.auto_pause_count || 0)}</div><div class="muted">Loss threshold recommendations</div></div>
        <div class="card"><div>Blocked Cap Breaches</div><div class="metric">${escapeHtml(data.blocked_count || 0)}</div><div class="muted">Above configured caps</div></div>
        <div class="card"><div>Platforms</div><div class="metric">${escapeHtml(Object.keys(data.by_platform || {}).length)}</div><div class="muted">${escapeHtml(compactCounts(data.by_platform))}</div></div>`;
      const tbody = document.querySelector('#budget-actions');
      const rows = data.recent_actions || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="muted">No active budget pacing actions. Loss controls and increase approvals will appear here after local evaluation.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(item => `
        <tr data-budget-action-id="${escapeHtml(item.id)}">
          <td><span class="pill ${item.action === 'block_increase' ? 'danger' : item.action === 'hold' ? 'ok' : 'warn'}">${escapeHtml(titleize(item.action))}</span></td>
          <td>${escapeHtml(titleize(item.status))}${item.approval_required ? '<div class="muted">Admin approval required</div>' : ''}</td>
          <td>${escapeHtml(item.platform)}</td>
          <td class="mono">${escapeHtml(item.external_campaign_id)}</td>
          <td>${escapeHtml(item.reason)}</td>
          <td class="mono">contact=${escapeHtml(item.safety?.would_contact_ads_provider)} | mutate=${escapeHtml(item.safety?.would_mutate_ads_provider)} | spend=${escapeHtml(item.safety?.would_spend_money)}</td>
        </tr>`).join('');
    }

    function renderLearningProposals(data) {
      const label = document.querySelector('#learning-proposals-label');
      const active = Number(data.active_count || 0);
      const approvals = Number(data.pending_approval_count || 0);
      const rollbacks = Number(data.rollback_count || 0);
      label.textContent = `${approvals} approvals`;
      label.className = `pill ${rollbacks || Number(data.rows_with_full_rollout_intent || 0) ? 'danger' : active ? 'warn' : 'ok'}`;
      document.querySelector('#learning-proposals-summary').innerHTML = `
        <div class="card"><div>Active Proposals</div><div class="metric">${escapeHtml(active)}</div><div class="muted">Replay/canary rows needing visibility</div></div>
        <div class="card"><div>Canary Active</div><div class="metric">${escapeHtml(data.canary_active_count || 0)}</div><div class="muted">Max canary: ${escapeHtml(data.max_canary_percent || 0)}%</div></div>
        <div class="card"><div>Pending Approval</div><div class="metric">${escapeHtml(approvals)}</div><div class="muted">100% rollout stays manual</div></div>
        <div class="card"><div>Rollbacks</div><div class="metric">${escapeHtml(rollbacks)}</div><div class="muted">Guardrail-triggered rollback states</div></div>
        <div class="card"><div>Target Areas</div><div class="metric">${escapeHtml(Object.keys(data.by_target_area || {}).length)}</div><div class="muted">${escapeHtml(compactCounts(data.by_target_area))}</div></div>`;
      const tbody = document.querySelector('#learning-proposals');
      const rows = data.recent_proposals || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="muted">No active learning proposals. Replay, canary, rollback, and approval states will appear here after Hermes creates local proposals.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(item => `
        <tr data-learning-proposal-id="${escapeHtml(item.id)}">
          <td>${escapeHtml(titleize(item.proposal_type))}<div class="muted">${escapeHtml(item.title)}</div></td>
          <td><span class="pill ${item.status === 'rollback_triggered' ? 'danger' : item.status === 'canary_active' ? 'ok' : 'warn'}">${escapeHtml(titleize(item.status))}</span>${item.approval_required ? '<div class="muted">Admin approval required</div>' : ''}</td>
          <td>${escapeHtml(item.target_area)}</td>
          <td class="mono">${escapeHtml(item.canary_percent)}%</td>
          <td class="mono">${escapeHtml(item.guardrail?.metric)}: ${escapeHtml(item.guardrail?.baseline_value ?? 'n/a')} -> ${escapeHtml(item.guardrail?.candidate_value ?? 'n/a')}</td>
          <td class="mono">route=${escapeHtml(item.safety?.would_route_live_traffic)} | promote=${escapeHtml(item.safety?.would_promote_without_admin_approval)} | full approval=${escapeHtml(item.safety?.requires_admin_approval_for_full_rollout)}</td>
        </tr>`).join('');
    }

    function exceptionActionButton(item, action, label) {
      return `<button type="button" class="secondary" data-exception-action="${escapeHtml(action)}" data-lead-id="${escapeHtml(item.lead_id || '')}" data-return-request-id="${escapeHtml(item.return_request_id || '')}">${escapeHtml(label)}</button>`;
    }

    function renderExceptions(data) {
      const tbody = document.querySelector('#exception-queue');
      const rows = data.exceptions || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="muted">No active autopilot exceptions. Normal eligible workflows are straight-through.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(item => {
        const context = [item.entity_type, item.lead_id ? `lead ${item.lead_id}` : '', item.buyer_id ? `buyer ${item.buyer_id}` : '', item.market || '', item.service || ''].filter(Boolean).join(' | ');
        const actions = [
          item.lead_id ? exceptionActionButton(item, 'open_timeline', 'Open Timeline') : '',
          item.actions?.includes('approve_lead') ? exceptionActionButton(item, 'approve_lead', 'Approve Lead') : '',
          item.actions?.includes('approve_return') ? exceptionActionButton(item, 'approve_return', 'Approve Return') : '',
          item.actions?.includes('reject_return') ? exceptionActionButton(item, 'reject_return', 'Reject Return') : '',
        ].filter(Boolean).join(' ');
        return `
          <tr data-exception-id="${escapeHtml(item.exception_id)}">
            <td><span class="pill ${item.severity === 'critical' ? 'danger' : item.severity === 'warning' ? 'warn' : 'ok'}">${escapeHtml(item.severity)}</span></td>
            <td>${escapeHtml(item.reason)}<div class="muted mono">${escapeHtml(item.kind)}</div></td>
            <td class="mono">${escapeHtml(context)}</td>
            <td>${escapeHtml(item.sla_age_minutes)} min</td>
            <td>${escapeHtml(item.recommended_action)}</td>
            <td><div class="actions">${actions || '<span class="muted">Review only</span>'}</div></td>
          </tr>`;
      }).join('');
      tbody.querySelectorAll('button[data-exception-action]').forEach(button => {
        button.addEventListener('click', async () => handleExceptionAction(button));
      });
    }

    async function handleExceptionAction(button) {
      const action = button.getAttribute('data-exception-action');
      const leadId = button.getAttribute('data-lead-id');
      const returnRequestId = button.getAttribute('data-return-request-id');
      if (action === 'open_timeline' && leadId) {
        document.querySelector('#timeline-lead-id').value = leadId;
        await loadTimeline(leadId);
        document.querySelector('#timeline-summary').scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
      button.disabled = true;
      try {
        if (action === 'approve_lead' && leadId) {
          await api(`/v1/admin/leads/${encodeURIComponent(leadId)}/review`, {
            method: 'POST',
            body: JSON.stringify({ action: 'approve', notes: 'Approved from Autopilot exception queue.', operator: 'local-admin' }),
          });
        } else if ((action === 'approve_return' || action === 'reject_return') && returnRequestId) {
          await api(`/v1/return-requests/${encodeURIComponent(returnRequestId)}/review`, {
            method: 'POST',
            body: JSON.stringify({ action: action === 'approve_return' ? 'approve' : 'reject', notes: 'Reviewed from Autopilot exception queue.', operator: 'local-admin' }),
          });
        }
        await loadAutopilot();
        setStatus(`Autopilot action ${action} completed.`, 'ok');
      } catch (err) {
        setStatus(`Autopilot action ${action} failed: ${err.message}`, 'error');
      } finally {
        button.disabled = false;
      }
    }

    async function loadAutopilot() {
      const [autopilotKpis, exceptions, exceptionSummary, budgetActions, learningProposals] = await Promise.all([
        api('/v1/admin/autopilot/kpis'),
        api('/v1/admin/autopilot/exceptions'),
        api('/v1/admin/autopilot/exception-queue/summary'),
        api('/v1/admin/autopilot/budget-actions/summary'),
        api('/v1/admin/autopilot/learning-proposals/summary'),
      ]);
      renderAutopilotKpis(autopilotKpis);
      renderExceptionSummary(exceptionSummary);
      renderBudgetActions(budgetActions);
      renderLearningProposals(learningProposals);
      renderExceptions(exceptions);
      return { autopilotKpis, exceptions, exceptionSummary, budgetActions, learningProposals };
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
      const summary = document.querySelector('#timeline-summary');
      const input = document.querySelector('#timeline-lead-id');
      summary.textContent = `Lead ${data.lead_id}\nCurrent state: ${data.current_state}\nStatus: ${lead.status || 'unknown'} | Service: ${lead.requested_service || 'unknown'} | Class: ${lead.lead_class || 'unknown'} | Hold: ${lead.hold_for_review ? 'yes' : 'no'}`;
      summary.className = 'status';
      summary.setAttribute('role', 'status');
      summary.setAttribute('aria-live', 'polite');
      input.setAttribute('aria-invalid', 'false');
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
      const normalizedLeadId = String(leadId || '').trim();
      const validationError = validateLeadId(normalizedLeadId);
      if (validationError) {
        setTimelineMessage(validationError, 'error');
        setStatus(validationError, 'error');
        document.querySelector('#timeline-lead-id').focus();
        return false;
      }
      setStatus(`Loading real audit timeline for lead ${normalizedLeadId}...`);
      try {
        const data = await api(`/v1/admin/leads/${encodeURIComponent(normalizedLeadId)}/timeline`);
        renderTimeline(data);
        setStatus(`Timeline loaded from lead_state_transitions. Events: ${(data.events || []).length}`);
        return true;
      } catch (err) {
        const message = `Timeline could not be loaded for ${normalizedLeadId}. Confirm the lead ID exists in local synthetic evidence, then try again.`;
        setTimelineMessage(message, 'error');
        setStatus(`${message}\n${err.message}`, 'error');
        return false;
      }
    }

    function renderBuyers(buyers) {
      const rows = buyers.buyers || [];
      document.querySelector('#buyer-count').textContent = `${rows.length} buyers`;
      document.querySelector('#buyers').innerHTML = rows.length ? rows.map(b => `
        <tr data-buyer-id="${escapeHtml(b.buyer_id)}">
          <td>${escapeHtml(b.company)}</td><td>${escapeHtml(b.status)}</td><td>${escapeHtml(b.sales_stage)}</td>
          <td>${money(b.deposit_balance_cents)}</td><td>${escapeHtml((b.services || []).join(', '))}</td>
          <td>${escapeHtml((b.target_zips || []).join(', '))}</td><td>${money(b.low_balance_threshold_cents)}</td><td class="mono">${escapeHtml(b.buyer_id)}</td>
        </tr>`).join('') : '<tr><td colspan="8" class="muted">No buyers have been created yet.</td></tr>';
      document.querySelectorAll('tr[data-buyer-id]').forEach(row => {
        row.addEventListener('click', () => {
          const buyerId = row.getAttribute('data-buyer-id');
          document.querySelector('#selected-buyer-id').value = buyerId;
          document.querySelector('#deposit-buyer-id').value = buyerId;
          setStatus(`Selected buyer ${buyerId} for update/deposit actions.`);
        });
      });
    }

    function updateBuyerWallet(buyerId, cents) {
      const row = Array.from(document.querySelectorAll('tr[data-buyer-id]')).find(candidate => candidate.getAttribute('data-buyer-id') === buyerId);
      if (row) row.children[3].textContent = money(cents);
    }

    async function load() {
      const [summary, buyers, workflowKpis, workflowRuns, readiness, autopilot] = await Promise.all([
        api('/v1/admin/kpis'),
        api('/v1/buyers'),
        api('/v1/admin/workflow-kpis'),
        api('/v1/admin/workflow-runs/recent'),
        api('/v1/admin/launch-readiness'),
        loadAutopilot(),
      ]);
      document.querySelector('#kpis').innerHTML = [
        ['Prepaid cash', money(summary.prepaid_cash_cents)],
        ['Active buyers', summary.active_buyers],
        ['Sold leads', summary.sold_leads],
        ['Returned leads', summary.returned_leads],
        ['Lead revenue', money(summary.lead_revenue_cents)],
      ].map(([label, value]) => `<div class="card"><div>${label}</div><div class="metric">${value}</div></div>`).join('');
      renderBuyers(buyers);
      renderWorkflowKpis(workflowKpis);
      renderWorkflowRuns(workflowRuns.runs || []);
      renderReadiness(readiness);
      setStatus(`Dashboard loaded from real APIs. Buyers: ${(buyers.buyers || []).length}. Open autopilot exceptions: ${(autopilot.exceptions.exceptions || []).length}`);
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
      setStatus(`Created real buyer ${buyer.company} (${buyer.buyer_id}).`, 'ok');
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
      setStatus(`Updated real buyer ${buyer.company}: ${buyer.status}/${buyer.sales_stage}.`, 'ok');
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
      updateBuyerWallet(raw.buyer_id, wallet.deposit_balance_cents);
      setStatus(`Deposit recorded. New wallet: ${money(wallet.deposit_balance_cents)}.`, 'ok');
      await load();
      setStatus(`Deposit recorded. New wallet: ${money(wallet.deposit_balance_cents)}.`, 'ok');
    });

    document.querySelector('#timeline-form').addEventListener('submit', async event => {
      event.preventDefault();
      const raw = formJson(event.currentTarget);
      await loadTimeline(raw.lead_id.trim());
    });

    async function reviewLead(action) {
      const leadId = document.querySelector('#timeline-lead-id').value.trim();
      const validationError = validateLeadId(leadId);
      if (validationError) {
        setTimelineMessage(validationError, 'error');
        setStatus(validationError, 'error');
        document.querySelector('#timeline-lead-id').focus();
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
      setStatus(`Dashboard load failed: ${err}`, 'error');
      document.body.insertAdjacentHTML('beforeend', `<pre role="alert">${escapeHtml(err)}</pre>`);
    });
  </script>
</body>
</html>
    """.replace(
        "__DEFAULT_BUYER_WEBHOOK_URL__",
        html.escape(_default_buyer_webhook_url("cowork-buyer"), quote=True),
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(content=b"", media_type="image/x-icon")


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
    raw_lead_id = payload.get("lead_id")
    if not raw_lead_id:
        raise HTTPException(400, "lead_id required")
    try:
        lead_uuid = UUID(str(raw_lead_id))
    except ValueError as e:
        raise HTTPException(400, "lead_id must be a UUID") from e
    try:
        async with get_session() as s:
            row = await s.get(LeadRow, lead_uuid)
            if row is None:
                raise HTTPException(404, "lead not found; verify the lead id and try again")
            lead = _row_to_lead(row)
        result = await run_auction(lead)
    except HTTPException:
        raise
    except Exception as e:
        delivered = await _latest_delivered_post_for_lead(lead_uuid)
        if delivered is not None:
            log.warning(
                "auction.trigger_idempotent_delivery_race",
                lead_id=str(lead_uuid),
                buyer_id=str(delivered.buyer_id),
                error=str(e),
            )
            return {
                "lead_id": str(lead_uuid),
                "pinged_buyer_ids": [],
                "winning_buyer_id": str(delivered.buyer_id),
                "winning_bid_cents": delivered.bid_cents,
                "duration_ms": 0,
            }
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
        api_key=uuid4().hex,
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
        follow_up_date=payload.next_follow_up_at,
        services=payload.services,
        services_offered=payload.services,
        target_zips=payload.target_zips,
        exclusive_zips=payload.exclusive_zips,
        low_balance_threshold=payload.low_balance_threshold,
        low_balance_threshold_cents=_decimal_to_cents(payload.low_balance_threshold),
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
            gross_lead_revenue = await s.scalar(
                select(func.coalesce(func.sum(PostResult.bid_cents), 0)).where(
                    PostResult.delivered.is_(True)
                )
            )
            buyer_adjustments = await s.scalar(
                select(func.coalesce(func.sum(BillingEvent.amount_cents), 0)).where(
                    BillingEvent.event_type == "lead.returned"
                )
            )
        lead_revenue_cents = int(lead_revenue or 0)
        gross_lead_revenue_cents = int(gross_lead_revenue or 0)
        buyer_adjustments_cents = int(buyer_adjustments or 0)
        return {
            "prepaid_cash_cents": _decimal_to_cents(Decimal(prepaid or 0)),
            "active_buyers": int(active_buyers or 0),
            "sold_leads": int(sold_leads or 0),
            "returned_leads": int(returned_leads or 0),
            "lead_revenue_cents": lead_revenue_cents,
            "gross_lead_revenue_cents": gross_lead_revenue_cents,
            "buyer_adjustments_cents": buyer_adjustments_cents,
            "campaign_spend_cents": 0,
            "campaign_margin_cents": gross_lead_revenue_cents - buyer_adjustments_cents,
            "campaign_margin_basis": "gross_lead_revenue_cents - buyer_adjustments_cents; campaign spend is not ingested in local proof",
        }
    except Exception as e:
        log.error("admin.kpis_failed", error=str(e))
        raise HTTPException(
            500, "admin kpis could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/admin/attribution/campaign/{campaign_id}")
async def admin_campaign_attribution(campaign_id: str) -> dict[str, Any] | None:
    roi = await get_campaign_roi(campaign_id)
    return asdict(roi) if roi is not None else None


@app.get("/v1/admin/attribution/by-zip")
async def admin_attribution_by_zip(
    state: str = Query(min_length=2, max_length=2),
) -> list[dict[str, Any]]:
    return await get_roi_by_zip(state)


@app.get("/v1/admin/ads/offline-conversions")
async def admin_ads_offline_conversions(
    market_state: str | None = Query(default=None, min_length=2, max_length=2),
    market_zip: str | None = Query(default=None, min_length=3, max_length=10),
    service: str | None = Query(default=None, min_length=1, max_length=64),
    campaign_id: str | None = Query(default=None, min_length=1, max_length=128),
    conversion_name: str = Query(default=ADS_DEFAULT_CONVERSION_NAME, min_length=1, max_length=128),
    campaign_budget_cents: int = Query(default=100_000, ge=0),
    planned_spend_cents: int = Query(default=0, ge=0),
    max_rows: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    """Build a local-only Google Ads offline conversion import preview."""
    conversion_name = _normalize_ads_conversion_name(conversion_name)
    if market_state and market_zip:
        raise HTTPException(400, "choose either market_state or market_zip, not both")
    dry_run_gate = provider_decision(
        ProviderArea.ADS,
        action="build dry-run offline conversion export",
    )
    if not dry_run_gate.allowed:
        raise HTTPException(
            403,
            {
                "message": "ads dry-run export is paused by provider safety settings",
                "provider_gate": _provider_decision_response(dry_run_gate),
            },
        )

    filters = [
        PostResult.delivered.is_(True),
        PostResult.returned.is_(False),
        LeadRow.google_click_id.is_not(None),
        LeadRow.google_click_id != "",
    ]
    buyer_filters = [BuyerRow.status == BuyerStatus.ACTIVE.value]
    if market_state:
        filters.append(LeadRow.state == market_state.upper())
    if market_zip:
        filters.append(LeadRow.zip == market_zip)
        buyer_filters.append(
            or_(
                BuyerRow.target_zips.contains([market_zip]),
                BuyerRow.exclusive_zips.contains([market_zip]),
            )
        )
    if service:
        normalized_service = service.strip().lower()
        filters.append(LeadRow.requested_service == normalized_service)
        buyer_filters.append(BuyerRow.services.contains([normalized_service]))
    if campaign_id:
        filters.append(LeadRow.campaign_id == campaign_id)

    try:
        async with get_session() as s:
            ranked_conversions = (
                select(
                    LeadRow.id.label("lead_id"),
                    PostResult.id.label("post_result_id"),
                    func.row_number()
                    .over(
                        partition_by=(LeadRow.id, LeadRow.google_click_id),
                        order_by=PostResult.created_at.desc(),
                    )
                    .label("conversion_rank"),
                )
                .join(PostResult, PostResult.lead_id == LeadRow.id)
                .where(and_(*filters))
                .subquery()
            )
            conversion_rows = (
                await s.execute(
                    select(LeadRow, PostResult)
                    .select_from(LeadRow)
                    .join(ranked_conversions, ranked_conversions.c.lead_id == LeadRow.id)
                    .join(PostResult, PostResult.id == ranked_conversions.c.post_result_id)
                    .where(ranked_conversions.c.conversion_rank == 1)
                    .order_by(PostResult.created_at.desc())
                    .limit(max_rows)
                )
            ).all()
            wallet_runway_cents = await s.scalar(
                select(func.coalesce(func.sum(BuyerRow.deposit_balance * 100), 0)).where(
                    and_(*buyer_filters)
                )
            )
    except Exception as e:
        log.error("admin.ads_offline_export_failed", error=str(e))
        raise HTTPException(
            500, "ads offline conversion preview could not be built from local data"
        ) from e

    export_rows = _ads_offline_conversion_rows(conversion_rows, conversion_name)
    attributed_value_cents = sum(int(row["conversion_value_cents"]) for row in export_rows)
    guardrails = _ads_spend_guardrail_preview(
        row_count=len(export_rows),
        attributed_conversion_value_cents=attributed_value_cents,
        campaign_budget_cents=campaign_budget_cents,
        planned_spend_cents=planned_spend_cents,
        wallet_runway_cents=int(wallet_runway_cents or 0),
        live_ads_approved=provider_live_approved(ProviderArea.ADS),
    )
    upload_gate = provider_decision(
        ProviderArea.ADS,
        action="upload offline conversions to ads provider",
        requires_live_approval=True,
        live_spend=True,
    )
    return {
        "mode": "dry_run",
        "would_contact_ads_provider": False,
        "would_upload": False,
        "scope": {
            "market_state": market_state.upper() if market_state else None,
            "market_zip": market_zip,
            "service": service.strip().lower() if service else None,
            "campaign_id": campaign_id,
            "max_rows": max_rows,
        },
        "provider_gate": {
            "dry_run": _provider_decision_response(dry_run_gate),
            "live_upload": _provider_decision_response(upload_gate),
        },
        "export": {
            "format": "google_ads_offline_conversion_csv",
            "columns": ADS_OFFLINE_CONVERSION_COLUMNS,
            "row_count": len(export_rows),
            "rows": export_rows,
            "csv_preview": _ads_offline_conversion_csv(export_rows),
            "pii_redacted": True,
            "excluded_fields": ["name", "phone_e164", "email", "address_line1"],
        },
        "guardrails": guardrails,
    }


@app.get("/v1/admin/export/mailer-csv")
async def admin_mailer_csv(
    state: str | None = Query(default=None, min_length=2, max_length=2),
    service: str | None = Query(default=None, min_length=1, max_length=64),
    status: str = Query(default="unsold", min_length=1, max_length=32),
) -> Response:
    csv_body = await export_mailer_csv(state, service, status)
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="stormlead-mailer.csv"'},
    )


@app.post("/v1/admin/guardrails/evaluate")
async def admin_evaluate_guardrails() -> dict[str, Any]:
    return {"actions": await evaluate_buyer_guardrails()}


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


@app.get("/v1/admin/autopilot/kpis")
async def admin_autopilot_kpis() -> dict[str, Any]:
    """Paid-pilot straight-through processing KPIs derived from local audit rows."""
    try:
        async with get_session() as s:
            leads = (await s.execute(select(LeadRow))).scalars().all()
            transitions = (
                (
                    await s.execute(
                        select(LeadStateTransition).order_by(LeadStateTransition.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            posts = (await s.execute(select(PostResult))).scalars().all()
            returns = (await s.execute(select(ReturnRequest))).scalars().all()
            buyers = (await s.execute(select(BuyerRow))).scalars().all()
            exceptions = await _build_autopilot_exceptions(s, limit=250)

        latest_by_lead: dict[UUID, LeadStateTransition] = {}
        events_by_lead: dict[UUID, set[str]] = {}
        for transition in transitions:
            latest_by_lead[transition.lead_id] = transition
            events_by_lead.setdefault(transition.lead_id, set()).add(transition.event_type)

        posts_by_lead: dict[UUID, list[PostResult]] = {}
        for post in posts:
            posts_by_lead.setdefault(post.lead_id, []).append(post)

        exclusion_counts: dict[str, int] = {}
        eligible = 0
        automated_successes = 0
        auto_sold = 0
        auto_rejected = 0
        manual_touched = 0
        for lead in leads:
            lead_events = events_by_lead.get(lead.id, set())
            manual_touch = any(event.startswith("admin.") for event in lead_events)
            if manual_touch:
                manual_touched += 1
            exclusions = _autopilot_exclusion_reasons(
                lead, latest_by_lead.get(lead.id), posts_by_lead.get(lead.id, [])
            )
            for reason in exclusions:
                exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
            if exclusions:
                continue
            if lead.status in AUTOPILOT_SUCCESS_STATES:
                eligible += 1
                if not manual_touch:
                    automated_successes += 1
                    if lead.status == "sold":
                        auto_sold += 1
                    if lead.status == "rejected":
                        auto_rejected += 1

        delivered_posts = sum(1 for post in posts if post.delivered)
        failed_posts = sum(1 for post in posts if not post.delivered)
        returned_posts = sum(1 for post in posts if post.returned)
        total_post_attempts = delivered_posts + failed_posts
        auto_decided_returns = sum(
            1
            for request in returns
            if request.status in {"approved", "rejected"}
            and request.reviewed_by == "autopilot-policy"
        )
        active_return_requests = sum(
            1 for request in returns if request.status in ACTIVE_RETURN_REQUEST_STATUSES
        )
        low_wallet_buyers = sum(
            1
            for buyer in buyers
            if buyer.status == BuyerStatus.ACTIVE.value
            and _decimal_to_cents(buyer.deposit_balance)
            <= _decimal_to_cents(buyer.low_balance_threshold)
        )
        revenue_leads = delivered_posts - returned_posts
        lead_revenue_cents = sum(
            post.bid_cents for post in posts if post.delivered and not post.returned
        )
        attributed_source_count = len(
            {lead.campaign_source for lead in leads if lead.campaign_source}
        )
        straight_through_rate = _normalize_ratio(automated_successes, eligible)
        exception_reason_counts: dict[str, int] = {}
        for item in exceptions:
            reason = str(item["reason"])
            exception_reason_counts[reason] = exception_reason_counts.get(reason, 0) + 1

        return {
            "schema_version": 1,
            "policy_version": AUTOPILOT_POLICY_VERSION,
            "target_straight_through_rate": 0.99,
            "straight_through_rate": straight_through_rate,
            "eligible_workflows": eligible,
            "automated_successes": automated_successes,
            "total_leads": len(leads),
            "open_exceptions": len(exceptions),
            "exclusion_counts": exclusion_counts,
            "exception_reason_counts": exception_reason_counts,
            "buyer_onboarding": {
                "total_buyers": len(buyers),
                "autopilot_ready_buyers": sum(
                    1 for buyer in buyers if _buyer_onboarding_readiness(buyer)["autopilot_ready"]
                ),
                "low_wallet_buyers": low_wallet_buyers,
            },
            "metrics": [
                _ratio_metric(
                    "straight_through_rate",
                    "Straight-through rate",
                    automated_successes,
                    eligible,
                    "No eligible paid-pilot workflows have completed yet",
                ),
                _ratio_metric(
                    "exception_rate",
                    "Exception rate",
                    len(exceptions),
                    max(len(leads), 1),
                    "No captured leads are available yet",
                ),
                _ratio_metric(
                    "auto_sold_lead_rate",
                    "Auto-sold lead rate",
                    auto_sold,
                    eligible,
                    "No eligible paid-pilot workflows have completed yet",
                ),
                _ratio_metric(
                    "auto_rejected_lead_rate",
                    "Auto-rejected lead rate",
                    auto_rejected,
                    eligible,
                    "No eligible paid-pilot workflows have completed yet",
                ),
                _ratio_metric(
                    "delivery_success_rate",
                    "Delivery success",
                    delivered_posts,
                    total_post_attempts,
                    "No post attempts have been recorded yet",
                ),
                _ratio_metric(
                    "refund_auto_decision_rate",
                    "Refund auto-decision",
                    auto_decided_returns,
                    len(returns),
                    "No return requests have been recorded yet",
                ),
                _ratio_metric(
                    "manual_touch_rate",
                    "Manual touch rate",
                    manual_touched,
                    max(len(leads), 1),
                    "No captured leads are available yet",
                ),
                _count_metric("open_exceptions", "Open exceptions", len(exceptions), "items"),
                _count_metric(
                    "active_return_requests", "Active returns", active_return_requests, "requests"
                ),
                _count_metric(
                    "buyer_wallet_failures", "Buyer wallet failures", low_wallet_buyers, "buyers"
                ),
                _money_metric(
                    "revenue_per_net_lead",
                    "Revenue / net lead",
                    (lead_revenue_cents / 100) / revenue_leads if revenue_leads else None,
                    "No net delivered leads are available yet",
                ),
                _count_metric(
                    "source_roi_inputs", "Source ROI inputs", attributed_source_count, "sources"
                ),
            ],
        }
    except Exception as e:
        log.error("admin.autopilot_kpis_failed", error=str(e))
        raise HTTPException(
            500, "autopilot kpis could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/admin/autopilot/exceptions")
async def admin_autopilot_exceptions(
    kind: str | None = Query(default=None, min_length=1, max_length=64),
    lead_id: UUID | None = None,
    buyer_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=250),
) -> dict[str, Any]:
    """Return unresolved operator work for the 1% exception queue without lead PII."""
    try:
        async with get_session() as s:
            exceptions = await _build_autopilot_exceptions(
                s, limit=limit, kind=kind, lead_id=lead_id, buyer_id=buyer_id
            )
        return {
            "schema_version": 1,
            "policy_version": AUTOPILOT_POLICY_VERSION,
            "exceptions": exceptions,
            "count": len(exceptions),
        }
    except Exception as e:
        log.error("admin.autopilot_exceptions_failed", error=str(e))
        raise HTTPException(
            500, "autopilot exceptions could not be loaded; retry after checking database health"
        ) from e


@app.post("/v1/admin/autopilot/exceptions/sync")
async def admin_autopilot_exceptions_sync(
    kind: str | None = Query(default=None, min_length=1, max_length=64),
    lead_id: UUID | None = None,
    buyer_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=250),
) -> dict[str, Any]:
    """Materialize computed operator exceptions into the durable local queue."""
    try:
        async with get_session() as s:
            exceptions = await _build_autopilot_exceptions(
                s, limit=limit, kind=kind, lead_id=lead_id, buyer_id=buyer_id
            )
            sync_summary = await _sync_exception_queue_items(s, exceptions)
        return {
            "schema_version": 1,
            "policy_version": AUTOPILOT_POLICY_VERSION,
            "mode": "local_exception_queue_sync",
            "would_contact_provider": False,
            "computed_count": len(exceptions),
            "sync": sync_summary,
        }
    except Exception as e:
        log.error("admin.autopilot_exceptions_sync_failed", error=str(e))
        raise HTTPException(
            500, "autopilot exceptions could not be synced; retry after checking database health"
        ) from e


@app.get("/v1/admin/autopilot/exception-queue/summary")
async def admin_autopilot_exception_queue_summary(
    limit: int = Query(default=250, ge=1, le=1000),
) -> dict[str, Any]:
    """Summarize durable exception_queue items for local operator dashboards."""
    try:
        async with get_session() as s:
            rows = (
                (
                    await s.execute(
                        select(ExceptionQueueItem)
                        .where(ExceptionQueueItem.status.in_(ACTIVE_EXCEPTION_QUEUE_STATUSES))
                        .order_by(ExceptionQueueItem.sla_due_at.asc().nulls_last())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return _exception_queue_dashboard_summary(rows)
    except Exception as e:
        log.error("admin.autopilot_exception_queue_summary_failed", error=str(e))
        raise HTTPException(
            500,
            "autopilot exception queue summary could not be loaded; retry after checking database health",
        ) from e


@app.get("/v1/admin/autopilot/budget-actions/summary")
async def admin_autopilot_budget_actions_summary(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Summarize local budget pacing actions for read-only admin review."""
    try:
        async with get_session() as s:
            rows = (
                (
                    await s.execute(
                        select(BudgetActionLog)
                        .where(BudgetActionLog.status.in_(ACTIVE_BUDGET_ACTION_STATUSES))
                        .order_by(BudgetActionLog.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        return _budget_action_dashboard_summary(rows, recent_limit=limit)
    except Exception as e:
        log.error("admin.autopilot_budget_actions_summary_failed", error=str(e))
        raise HTTPException(
            500,
            "autopilot budget action summary could not be loaded; retry after checking database health",
        ) from e


@app.get("/v1/admin/autopilot/learning-proposals/summary")
async def admin_autopilot_learning_proposals_summary(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Summarize local learning proposal replay/canary state for read-only review."""
    try:
        async with get_session() as s:
            rows = (
                (
                    await s.execute(
                        select(LearningProposal)
                        .where(LearningProposal.status.in_(ACTIVE_LEARNING_PROPOSAL_STATUSES))
                        .order_by(LearningProposal.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        return _learning_proposal_dashboard_summary(rows, recent_limit=limit)
    except Exception as e:
        log.error("admin.autopilot_learning_proposals_summary_failed", error=str(e))
        raise HTTPException(
            500,
            "autopilot learning proposal summary could not be loaded; retry after checking database health",
        ) from e


@app.get("/v1/admin/provider-kill-switches")
async def admin_provider_kill_switches() -> dict[str, Any]:
    snapshot = provider_pause_snapshot()
    paused = sorted(area for area, item in snapshot.items() if item["paused"])
    return {
        "schema_version": 1,
        "kill_switches": snapshot,
        "paused_areas": paused,
        "paused_count": len(paused),
        "change_plan_endpoint": "/v1/admin/provider-kill-switches/change-plan",
        "would_contact_provider": False,
        "safe_to_call_without_provider_credentials": True,
    }


@app.post("/v1/admin/provider-kill-switches/change-plan")
async def admin_provider_kill_switch_change_plan(
    request: ProviderKillSwitchChangePlanRequest,
) -> dict[str, Any]:
    plan = provider_kill_switch_change_plan(
        request.area,
        desired_paused=request.desired_paused,
        reason=request.reason.strip(),
    )
    return {
        "mode": "local_provider_kill_switch_change_plan",
        "plan": plan,
        "current_snapshot": provider_pause_snapshot()[request.area.value],
        "would_contact_provider": False,
        "would_mutate_runtime": False,
        "safe_to_call_without_provider_credentials": True,
    }


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
            latest = await latest_state(s, lead_id)
            current_state = latest.value if latest is not None else lead.status
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
async def get_buyer(buyer_id: UUID, request: Request) -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            _require_buyer_api_key(request, buyer)
            return _buyer_response(buyer)
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.lookup_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(
            500, "buyer could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/buyers/{buyer_id}/sandbox-certification")
async def get_buyer_sandbox_certification(buyer_id: UUID, request: Request) -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            _require_buyer_api_key(request, buyer)
            return _buyer_sandbox_certification_response(buyer)
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.sandbox_certification_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(
            500,
            "buyer sandbox certification could not be built; verify the buyer and retry",
        ) from e


@app.post("/v1/buyers/{buyer_id}/api-key/rotate")
async def rotate_buyer_api_key(
    buyer_id: UUID, request: Request, response: Response
) -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            if not (
                _buyer_api_key_matches(request, buyer)
                or _operator_token_supplied_and_authorized(request)
            ):
                raise HTTPException(401, "valid buyer API key or operator token required")
            old_api_key_set = bool(buyer.api_key)
            api_key = _new_buyer_api_key()
            buyer.api_key = api_key
            await s.flush()
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
            return {
                "buyer_id": str(buyer.id),
                "api_key": api_key,
                "api_key_set": True,
                "old_api_key_set": old_api_key_set,
                "rotated_at": datetime.now(UTC).isoformat(),
                "warning": "Store this key now; it is returned once by this rotation response.",
            }
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.api_key_rotate_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(500, "buyer API key could not be rotated; verify auth and retry") from e


@app.patch("/v1/buyers/{buyer_id}")
async def update_buyer(buyer_id: UUID, payload: BuyerUpdateRequest) -> dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    requested_active_status = updates.get("status") in {
        BuyerStatus.ACTIVE,
        BuyerStatus.ACTIVE.value,
    }
    readiness_relevant_update = bool(BUYER_ACTIVATION_FIELDS.intersection(updates))
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
                if key == "services":
                    buyer.services_offered = value
                elif key == "next_follow_up_at":
                    buyer.follow_up_date = value
                elif key == "low_balance_threshold":
                    buyer.low_balance_threshold_cents = _decimal_to_cents(value)
            if requested_active_status:
                await _assert_no_exclusive_zip_conflict(
                    buyer.exclusive_zips or [], exclude_buyer_id=buyer_id
                )
            readiness = _buyer_onboarding_readiness(buyer)
            if (
                buyer.status == BuyerStatus.ACTIVE.value
                and readiness_relevant_update
                and not readiness["autopilot_ready"]
            ):
                missing = ", ".join(readiness["missing_requirements"])
                raise HTTPException(
                    409,
                    f"buyer is not activation ready; missing requirements: {missing}",
                )
            await s.flush()
            return _buyer_response(buyer)
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.update_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(500, "buyer could not be updated; verify the request and retry") from e


@app.get("/v1/buyers/{buyer_id}/wallet")
async def get_wallet(buyer_id: UUID, request: Request) -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            _require_buyer_api_key(request, buyer)
            return _buyer_wallet_response(buyer)
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.wallet_lookup_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(
            500, "wallet could not be loaded; retry after checking database health"
        ) from e


@app.get("/v1/buyers/{buyer_id}/wallet/reconciliation")
async def get_wallet_reconciliation(buyer_id: UUID, request: Request) -> dict[str, Any]:
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            _require_buyer_api_key(request, buyer)
            ledger_total = await s.scalar(
                select(func.coalesce(func.sum(BillingEvent.amount_cents), 0)).where(
                    BillingEvent.buyer_id == buyer_id
                )
            )
            recent_funding_events = (
                (
                    await s.execute(
                        select(BillingEvent)
                        .where(
                            BillingEvent.buyer_id == buyer_id,
                            BillingEvent.event_type == "deposit.added",
                        )
                        .order_by(BillingEvent.created_at.desc())
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )
            return _wallet_reconciliation_payload(
                buyer,
                ledger_total_cents=int(ledger_total or 0),
                recent_funding_events=recent_funding_events,
            )
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.wallet_reconciliation_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(
            500, "wallet reconciliation could not be loaded; retry after checking database health"
        ) from e


@app.post("/v1/buyers/{buyer_id}/wallet/refill-intents")
async def create_wallet_refill_intent(
    buyer_id: UUID, payload: WalletRefillIntentRequest, request: Request
) -> dict[str, Any]:
    decision = (
        _stripe_sandbox_payment_decision("create Stripe sandbox buyer wallet refill intent")
        if payload.provider == "stripe"
        else _payment_provider_decision(
            payload.provider, action="create buyer wallet refill intent"
        )
    )
    if not decision.allowed:
        raise _payment_http_exception(
            403,
            "payment provider action is not approved",
            "payment_provider_not_approved",
            provider_gate=_provider_decision_response(decision),
            approval_packet=_payment_approval_packet(),
        )
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise _payment_http_exception(
                    404,
                    "buyer not found; verify the buyer id and try again",
                    "payment_buyer_not_found",
                )
            if payload.provider == "stripe":
                return await _stripe_wallet_refill_intent_response(
                    buyer, payload, decision, request
                )
            return _wallet_refill_intent_response(buyer, payload, decision)
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.wallet_refill_intent_failed", buyer_id=str(buyer_id), error=str(e))
        raise _payment_http_exception(
            500,
            "wallet refill intent could not be created; retry after checking database health",
            "wallet_refill_intent_failed",
        ) from e


@app.post("/v1/buyers/{buyer_id}/deposits")
async def add_deposit(buyer_id: UUID, payload: DepositRequest, request: Request) -> dict[str, Any]:
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


@app.post("/v1/payments/refill-events")
async def ingest_payment_refill_event(payload: PaymentRefillEventRequest) -> dict[str, Any]:
    decision = _payment_provider_decision(
        payload.provider, action="credit buyer wallet from payment event"
    )
    if not decision.allowed:
        raise _payment_http_exception(
            403,
            "payment provider action is not approved",
            "payment_provider_not_approved",
            provider_gate=_provider_decision_response(decision),
            approval_packet=_payment_approval_packet(),
        )
    if payload.provider != "local":
        raise _payment_http_exception(
            403,
            "live payment events require signed Stripe webhook verification before wallet crediting",
            "live_payment_requires_signed_webhook",
            provider_gate=_provider_decision_response(decision),
            approval_packet=_payment_approval_packet(),
        )
    return await _credit_payment_refill_event(payload, decision=decision)


@app.post("/v1/payments/stripe/refill-webhook")
async def ingest_stripe_refill_webhook(request: Request) -> dict[str, Any]:
    raw_body = await _read_stripe_webhook_body(request)
    event = _verified_stripe_event(raw_body, request.headers.get("stripe-signature", ""))
    payload = _stripe_refill_event_payload(event)
    decision = _stripe_sandbox_payment_decision("credit buyer wallet from signed Stripe webhook")
    if not decision.allowed:
        raise _payment_http_exception(
            403,
            "Stripe sandbox payment webhook is not approved or configured",
            "stripe_webhook_not_approved",
            provider_gate=_provider_decision_response(decision),
            approval_packet=_payment_approval_packet(),
        )
    return await _credit_payment_refill_event(payload, decision=decision)


async def _credit_payment_refill_event(
    payload: PaymentRefillEventRequest, *, decision: Any
) -> dict[str, Any]:
    if payload.status not in PAYMENT_CREDITABLE_STATUSES:
        raise _payment_http_exception(
            409,
            "payment event status is not creditable",
            "payment_status_not_creditable",
        )
    try:
        conflict_detail: str | None = None
        async with get_session() as s:
            await _lock_payment_refill_idempotency_scope(s, payload)
            buyer = await s.get(BuyerRow, payload.buyer_id, with_for_update=True)
            if buyer is None:
                raise _payment_http_exception(
                    404,
                    "buyer not found; verify the buyer id and try again",
                    "payment_buyer_not_found",
                )
            existing = await _existing_payment_refill_event(
                s,
                provider=payload.provider,
                buyer_id=payload.buyer_id,
                provider_event_id=payload.provider_event_id,
                payment_intent_id=payload.payment_intent_id,
                idempotency_key=payload.idempotency_key,
            )
            if existing is not None:
                event_matches = _payment_refill_event_matches(existing, payload)
                webhook_event = None
                if existing.external_event_id != payload.provider_event_id:
                    webhook_event = await _record_payment_refill_webhook_audit(
                        s, payload, status="ignored" if event_matches else "failed"
                    )
                if not event_matches:
                    conflict_detail = (
                        "payment refill idempotency conflict; reconcile wallet ledger "
                        "before retrying"
                    )
                else:
                    return _payment_refill_event_response(
                        buyer=buyer,
                        payload=payload,
                        decision=decision,
                        billing_event=existing,
                        idempotent_replay=True,
                        webhook_event=webhook_event,
                    )

            if existing is None:
                webhook_event = await _record_payment_refill_webhook_audit(
                    s, payload, status="processed"
                )

                amount = Decimal(payload.amount_cents) / Decimal(100)
                buyer.deposit_balance += amount
                billing_event = BillingEvent(
                    buyer_id=buyer.id,
                    lead_id=None,
                    event_type="deposit.added",
                    amount_cents=payload.amount_cents,
                    external_event_id=payload.provider_event_id,
                    metadata_json={
                        "source": "payment_refill_event",
                        "payment_provider": payload.provider,
                        "payment_event_id": payload.provider_event_id,
                        "payment_intent_id": payload.payment_intent_id,
                        "payment_webhook_event_id": str(webhook_event.id),
                        "idempotency_key": payload.idempotency_key,
                        "currency": payload.currency,
                        "local_simulation": payload.provider == "local",
                        "metadata": _safe_payment_metadata(payload.metadata),
                    },
                )
                s.add(billing_event)
                await s.flush()
                return _payment_refill_event_response(
                    buyer=buyer,
                    payload=payload,
                    decision=decision,
                    billing_event=billing_event,
                    idempotent_replay=False,
                    webhook_event=webhook_event,
                )
        if conflict_detail is not None:
            raise _payment_http_exception(
                409,
                conflict_detail,
                "payment_refill_idempotency_conflict",
            )
        raise RuntimeError("payment refill event reached an unreachable state")
    except HTTPException:
        raise
    except Exception as e:
        log.error(
            "payments.refill_event_failed",
            buyer_id=str(payload.buyer_id),
            provider=payload.provider,
            provider_event_id=payload.provider_event_id,
            error=str(e),
        )
        raise _payment_http_exception(
            500,
            "payment refill event could not be recorded; reconcile before retrying",
            "payment_refill_record_failed",
        ) from e


@app.post("/v1/leads/{lead_id}/return")
async def return_lead(
    lead_id: UUID, payload: ReturnLeadRequest, request: Request
) -> dict[str, Any]:
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
            buyer = await s.get(BuyerRow, result.buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer for delivered lead sale was not found")
            _require_buyer_api_key(request, buyer)
            if result.returned:
                raise HTTPException(
                    409, "lead was already returned; check the existing return record"
                )
            active_request = (
                (
                    await s.execute(
                        select(ReturnRequest)
                        .where(
                            ReturnRequest.post_result_id == result.id,
                            ReturnRequest.status.in_(ACTIVE_RETURN_REQUEST_STATUSES),
                        )
                        .order_by(ReturnRequest.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            if active_request is not None:
                raise HTTPException(
                    409,
                    f"active return request already exists: {active_request.id}",
                )

            return_request = ReturnRequest(
                post_result_id=result.id,
                lead_id=lead_id,
                buyer_id=result.buyer_id,
                reason=payload.reason,
                notes=payload.notes,
                evidence_json=payload.evidence,
                status="pending_review",
                requested_by=payload.requested_by,
            )
            s.add(return_request)
            await s.flush()
            current_state = await latest_state(s, lead_id) or PipelineState.SOLD
            await record_transition(
                s,
                lead_id=lead_id,
                from_state=None,
                to_state=current_state,
                event_type="lead.return_requested",
                task_name="buyer.return_request",
                status="pending_review",
                idempotency_key=build_transition_idempotency_key(
                    lead_id=lead_id,
                    from_state=None,
                    to_state=current_state,
                    event_type="lead.return_requested",
                    task_name="buyer.return_request",
                    version=f"return:{return_request.id}:requested",
                ),
                payload={
                    "return_request_id": str(return_request.id),
                    "post_result_id": str(result.id),
                    "buyer_id": str(result.buyer_id),
                    "reason": payload.reason,
                    "notes_present": bool(payload.notes),
                    "evidence_keys": sorted(payload.evidence.keys()),
                },
            )
            auto_action = None
            if payload.reason in AUTO_RETURN_APPROVE_REASONS:
                auto_action = "approve"
            elif payload.reason in AUTO_RETURN_REJECT_REASONS:
                auto_action = "reject"
            if auto_action:
                decision = await _apply_return_decision(
                    s,
                    return_request,
                    result,
                    buyer,
                    action=auto_action,
                    operator="autopilot-policy",
                    notes=f"Auto-{auto_action} by {AUTOPILOT_POLICY_VERSION} for reason {payload.reason}.",
                    task_name="autopilot.return_policy",
                    policy_version=AUTOPILOT_POLICY_VERSION,
                )
                decision["return_reason"] = payload.reason
                return decision
            return {
                "lead_id": str(lead_id),
                "buyer_id": str(result.buyer_id),
                "return_request_id": str(return_request.id),
                "status": return_request.status,
                "credited_cents": 0,
                "auto_decided": False,
                "policy_version": AUTOPILOT_POLICY_VERSION,
                "return_reason": payload.reason,
            }
    except HTTPException:
        raise
    except Exception as e:
        log.error("lead.return_failed", lead_id=str(lead_id), error=str(e))
        raise HTTPException(
            500, "lead return could not be recorded; retry or contact support"
        ) from e


@app.post("/v1/return-requests/{return_request_id}/review")
async def review_return_request(
    return_request_id: UUID, payload: ReturnReviewRequest
) -> dict[str, Any]:
    try:
        async with get_session() as s:
            request = await s.get(ReturnRequest, return_request_id)
            if request is None:
                raise HTTPException(404, "return request not found; verify the id and try again")
            if request.status in {"approved", "rejected"}:
                raise HTTPException(409, f"return request is already {request.status}")
            result = await s.get(PostResult, request.post_result_id)
            if result is None:
                raise HTTPException(404, "post result for this return request was not found")
            buyer = await s.get(BuyerRow, request.buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer for this return request was not found")

            return await _apply_return_decision(
                s,
                request,
                result,
                buyer,
                action=payload.action,
                operator=payload.operator,
                notes=payload.notes,
                task_name="admin.return_review",
            )
    except HTTPException:
        raise
    except Exception as e:
        log.error("return.review_failed", return_request_id=str(return_request_id), error=str(e))
        raise HTTPException(
            500, "return request review could not be recorded; retry or contact support"
        ) from e


@app.get("/v1/buyers/{buyer_id}/daily-report")
async def buyer_daily_report(buyer_id: UUID, request: Request) -> dict[str, Any]:
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        async with get_session() as s:
            buyer = await s.get(BuyerRow, buyer_id)
            if buyer is None:
                raise HTTPException(404, "buyer not found; verify the buyer id and try again")
            _require_buyer_api_key(request, buyer)
            delivered = await s.scalar(
                select(func.count(PostResult.id)).where(
                    PostResult.buyer_id == buyer_id,
                    PostResult.delivered.is_(True),
                    PostResult.created_at >= day_start,
                )
            )
            gross_spend = await s.scalar(
                select(func.coalesce(func.sum(PostResult.bid_cents), 0)).where(
                    PostResult.buyer_id == buyer_id,
                    PostResult.delivered.is_(True),
                    PostResult.created_at >= day_start,
                )
            )
            returned = await s.scalar(
                select(func.count(PostResult.id)).where(
                    PostResult.buyer_id == buyer_id,
                    PostResult.delivered.is_(True),
                    PostResult.returned.is_(True),
                    PostResult.created_at >= day_start,
                )
            )
            credits = await s.scalar(
                select(func.coalesce(func.sum(BillingEvent.amount_cents), 0)).where(
                    BillingEvent.buyer_id == buyer_id,
                    BillingEvent.event_type == "lead.returned",
                    BillingEvent.created_at >= day_start,
                )
            )
            pending_returns = await s.scalar(
                select(func.count(ReturnRequest.id)).where(
                    ReturnRequest.buyer_id == buyer_id,
                    ReturnRequest.status.in_(ACTIVE_RETURN_REQUEST_STATUSES),
                )
            )
            recent_returns = (
                (
                    await s.execute(
                        select(ReturnRequest)
                        .where(ReturnRequest.buyer_id == buyer_id)
                        .order_by(ReturnRequest.created_at.desc())
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )
            delivered_lead_details = (
                await s.execute(
                    select(PostResult, LeadRow)
                    .join(LeadRow, LeadRow.id == PostResult.lead_id)
                    .where(
                        PostResult.buyer_id == buyer_id,
                        PostResult.delivered.is_(True),
                        PostResult.created_at >= day_start,
                    )
                    .order_by(PostResult.created_at.desc())
                    .limit(25)
                )
            ).all()

            balance_cents = _decimal_to_cents(buyer.deposit_balance)
            threshold_cents = _decimal_to_cents(buyer.low_balance_threshold)
            refill_cents = _recommended_refill_cents(
                balance_cents=balance_cents,
                threshold_cents=threshold_cents,
                monthly_budget_cents=_decimal_to_cents(buyer.monthly_budget),
                delivered_today=int(delivered or 0),
                gross_spend_today_cents=int(gross_spend or 0),
            )
            delivered_lead_detail_rows = [
                {
                    "lead_id": str(lead.id),
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    "delivered_at": post.created_at.isoformat() if post.created_at else None,
                    "state": lead.state,
                    "zip": lead.zip,
                    "requested_service": lead.requested_service,
                    "lead_class": lead.lead_class,
                    "bid_cents": post.bid_cents,
                    "returned": post.returned,
                    "status": "returned" if post.returned else "delivered",
                }
                for post, lead in delivered_lead_details
            ]
            return {
                "buyer": _buyer_wallet_response(buyer),
                "window": {"start_at": day_start.isoformat(), "end_at": now.isoformat()},
                "delivery": {
                    "delivered_leads": int(delivered or 0),
                    "gross_spend_cents": int(gross_spend or 0),
                    "returned_leads": int(returned or 0),
                    "approved_return_credits_cents": int(credits or 0),
                    "pending_return_requests": int(pending_returns or 0),
                    "daily_cap_remaining": max(buyer.daily_cap - int(delivered or 0), 0),
                },
                "wallet": {
                    "low_balance_threshold_cents": threshold_cents,
                    "below_threshold": balance_cents <= threshold_cents,
                    "recommended_refill_cents": refill_cents,
                },
                "delivered_lead_details": delivered_lead_detail_rows,
                "delivered_leads": delivered_lead_detail_rows,
                "recent_return_requests": [_return_request_response(row) for row in recent_returns],
            }
    except HTTPException:
        raise
    except Exception as e:
        log.error("buyer.daily_report_failed", buyer_id=str(buyer_id), error=str(e))
        raise HTTPException(
            500, "buyer daily report could not be loaded; retry after checking database health"
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


def _sum_agent_cost(payloads: Sequence[Mapping[str, Any]]) -> float:
    total = 0.0
    for payload in payloads:
        try:
            total += float(payload.get("estimated_cost_usd") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _recommended_refill_cents(
    *,
    balance_cents: int,
    threshold_cents: int,
    monthly_budget_cents: int,
    delivered_today: int,
    gross_spend_today_cents: int,
) -> int:
    if balance_cents > threshold_cents:
        return 0
    average_bid_cents = gross_spend_today_cents // delivered_today if delivered_today else 0
    three_lead_buffer_cents = average_bid_cents * 3
    monthly_buffer_cents = monthly_budget_cents // 4
    return max(threshold_cents - balance_cents, three_lead_buffer_cents, monthly_buffer_cents)


def _ads_offline_conversion_rows(
    conversion_rows: Sequence[Any], conversion_name: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    sorted_rows = sorted(
        conversion_rows,
        key=lambda item: _ads_conversion_datetime(item[0], item[1]),
        reverse=True,
    )
    for lead, post in sorted_rows:
        gclid = str(getattr(lead, "google_click_id", "") or "").strip()
        if not gclid or not _is_valid_ads_click_id(gclid):
            continue
        dedupe_key = (str(lead.id), gclid)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        bid_cents = int(getattr(post, "bid_cents", 0) or 0)
        if bid_cents <= 0:
            continue
        conversion_time = _ads_conversion_datetime(lead, post)
        rows.append(
            {
                "Google Click ID": gclid,
                "Conversion Name": conversion_name,
                "Conversion Time": _format_ads_conversion_time(conversion_time),
                "Conversion Value": f"{bid_cents / 100:.2f}",
                "Conversion Currency": "USD",
                "Order ID": f"lead:{lead.id}",
                "conversion_value_cents": bid_cents,
                "redacted_context": {
                    "lead_id": str(lead.id),
                    "campaign_id": getattr(lead, "campaign_id", None),
                    "campaign_source": getattr(lead, "campaign_source", None),
                    "state": getattr(lead, "state", None),
                    "zip": getattr(lead, "zip", None),
                    "requested_service": getattr(lead, "requested_service", None),
                    "lead_class": getattr(lead, "lead_class", None),
                    "post_result_id": str(post.id),
                },
            }
        )
    return rows


def _is_valid_ads_click_id(value: str) -> bool:
    return bool(ADS_CLICK_ID_RE.fullmatch(value))


def _normalize_ads_conversion_name(value: str) -> str:
    normalized = value.strip()
    if not normalized or not ADS_CONVERSION_NAME_RE.fullmatch(normalized):
        raise HTTPException(
            400,
            "conversion_name must start with a letter or number and contain only safe CSV characters",
        )
    return normalized


def _ads_conversion_datetime(lead: Any, post: Any) -> datetime:
    value = getattr(post, "created_at", None) or getattr(lead, "created_at", None)
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=UTC)
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _format_ads_conversion_time(value: datetime) -> str:
    utc_value = value.astimezone(UTC)
    raw = utc_value.strftime("%Y-%m-%d %H:%M:%S%z")
    return f"{raw[:-2]}:{raw[-2:]}"


def _ads_offline_conversion_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=ADS_OFFLINE_CONVERSION_COLUMNS, extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def _ads_spend_guardrail_preview(
    *,
    row_count: int,
    attributed_conversion_value_cents: int,
    campaign_budget_cents: int,
    planned_spend_cents: int,
    wallet_runway_cents: int,
    live_ads_approved: bool,
) -> dict[str, Any]:
    planned_spend_within_budget = planned_spend_cents <= campaign_budget_cents
    wallet_runway_ready = wallet_runway_cents >= campaign_budget_cents
    conversions_present = row_count > 0
    value_covers_planned_spend = (
        attributed_conversion_value_cents >= planned_spend_cents
        if planned_spend_cents > 0
        else conversions_present
    )
    dry_run_ready = (
        conversions_present
        and planned_spend_within_budget
        and wallet_runway_ready
        and value_covers_planned_spend
    )
    live_upload_ready = dry_run_ready and live_ads_approved
    actions: list[str] = []
    if not conversions_present:
        actions.append("collect_attributed_sold_lead_evidence")
    if not planned_spend_within_budget:
        actions.append("reduce_planned_spend_to_campaign_budget")
    if not wallet_runway_ready:
        actions.append("fund_buyer_wallets_before_spend")
    if not value_covers_planned_spend:
        actions.append("review_unit_economics_before_spend")
    if not live_ads_approved:
        actions.append("approval_required_before_live_ads_upload")
    return {
        "decision": "live_upload_ready"
        if live_upload_ready
        else "dry_run_ready"
        if dry_run_ready
        else "not_ready",
        "dry_run_ready": dry_run_ready,
        "live_upload_ready": live_upload_ready,
        "checks": {
            "conversions_present": conversions_present,
            "planned_spend_within_budget": planned_spend_within_budget,
            "wallet_runway_covers_campaign_budget": wallet_runway_ready,
            "attributed_value_covers_planned_spend": value_covers_planned_spend,
            "live_ads_approved": live_ads_approved,
        },
        "metrics": {
            "row_count": row_count,
            "attributed_conversion_value_cents": attributed_conversion_value_cents,
            "campaign_budget_cents": campaign_budget_cents,
            "planned_spend_cents": planned_spend_cents,
            "wallet_runway_cents": wallet_runway_cents,
        },
        "recommended_actions": actions,
    }


def _payment_provider_decision(provider: str, *, action: str):
    live_provider = provider != "local"
    return provider_decision(
        ProviderArea.PAYMENTS,
        action=action,
        requires_live_approval=live_provider,
        live_money=live_provider,
    )


def _stripe_secret_key() -> str:
    return os.getenv("STRIPE_SECRET_KEY", "").strip()


def _stripe_webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()


def _stripe_key_mode() -> str:
    key = _stripe_secret_key()
    if key.startswith("sk_test_"):
        return "sandbox"
    if key.startswith("sk_live_"):
        return "live"
    return "missing"


def _stripe_sandbox_configured() -> bool:
    return _stripe_key_mode() == "sandbox" and _stripe_webhook_secret().startswith("whsec_")


def _stripe_sandbox_payment_decision(action: str) -> ProviderDecision:
    base = provider_decision(ProviderArea.PAYMENTS, action=action)
    if not base.allowed:
        return base
    if not _truthy_env(STRIPE_SANDBOX_APPROVAL_ENV):
        return ProviderDecision(
            ProviderArea.PAYMENTS,
            False,
            "Stripe sandbox payment action is not approved",
            action,
            external=True,
        )
    if not _stripe_sandbox_configured():
        return ProviderDecision(
            ProviderArea.PAYMENTS,
            False,
            "Stripe sandbox secret key and webhook secret are not configured",
            action,
            external=True,
        )
    return ProviderDecision(
        ProviderArea.PAYMENTS,
        True,
        "Stripe sandbox provider action approved",
        action,
        external=True,
        live_mode=False,
    )


def _provider_decision_response(decision: Any) -> dict[str, Any]:
    return {
        "area": decision.area.value,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "action": decision.action,
        "external": decision.external,
        "live_mode": decision.live_mode,
        "target_url": decision.target_url,
    }


def _payment_approval_packet() -> dict[str, Any]:
    approved = provider_live_approved(ProviderArea.PAYMENTS)
    sandbox_configured = _stripe_sandbox_configured()
    return {
        "status": "approved" if approved else "approval_required",
        "required": not approved,
        "requested_action": "Approve Stripe sandbox/live payment provider setup for buyer wallet refills.",
        "scope": "Create Stripe Checkout or PaymentIntent sessions and accept signed Stripe webhook credits for buyer wallet deposits.",
        "sandbox": {
            "approved": _truthy_env(STRIPE_SANDBOX_APPROVAL_ENV),
            "configured": sandbox_configured,
            "key_mode": _stripe_key_mode(),
            "required_env": [
                f"{STRIPE_SANDBOX_APPROVAL_ENV}=true",
                "STRIPE_SECRET_KEY=sk_test_<local secret store>",
                "STRIPE_WEBHOOK_SECRET=whsec_<local secret store>",
            ],
        },
        "required_env": [
            "STORMLEAD_APPROVE_PAYMENTS_LIVE=true",
            "STRIPE_SECRET_KEY=<local secret store>",
            "STRIPE_WEBHOOK_SECRET=<local secret store>",
        ],
        "risk": "Incorrect live payment setup can charge buyers or credit wallets without settled funds.",
        "safe_alternative": "Use provider=local refill intents plus POST /v1/payments/refill-events with synthetic local events.",
        "rollback": "Pause payments with STORMLEAD_PAUSE_PAYMENTS=true and reconcile billing_events against buyer.deposit_balance before re-enabling routing.",
    }


def _refill_idempotency_key(
    *, buyer_id: UUID, amount_cents: int, currency: str, supplied: str | None
) -> str:
    scope = f"buyer-wallet-refill:{buyer_id}:{amount_cents}:{currency.lower()}"
    return f"{scope}:{supplied}" if supplied else scope


def _payment_intent_id(provider: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{provider}:{idempotency_key}".encode()).hexdigest()[:24]
    prefix = "local_pi" if provider == "local" else f"{provider}_pi"
    return f"{prefix}_{digest}"


def _wallet_refill_intent_response(
    buyer: BuyerRow, payload: WalletRefillIntentRequest, decision: Any
) -> dict[str, Any]:
    idempotency_key = _refill_idempotency_key(
        buyer_id=buyer.id,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        supplied=payload.idempotency_key,
    )
    payment_intent_id = _payment_intent_id(payload.provider, idempotency_key)
    event_payload = {
        "provider": payload.provider,
        "provider_event_id": f"evt_{payment_intent_id}",
        "payment_intent_id": payment_intent_id,
        "buyer_id": str(buyer.id),
        "amount_cents": payload.amount_cents,
        "currency": payload.currency,
        "status": "succeeded",
        "idempotency_key": idempotency_key,
        "metadata": {"description": payload.description or "buyer wallet refill"},
    }
    return {
        "buyer_id": str(buyer.id),
        "provider": payload.provider,
        "mode": "local_simulation" if payload.provider == "local" else "live_provider",
        "payment_intent_id": payment_intent_id,
        "amount_cents": payload.amount_cents,
        "currency": payload.currency,
        "status": "requires_refill_event",
        "idempotency_key": idempotency_key,
        "provider_gate": _provider_decision_response(decision),
        "live_payment_approval": _payment_approval_packet(),
        "checkout_contract": {
            "type": "local_refill_event"
            if payload.provider == "local"
            else "stripe_checkout_pending",
            "live_checkout_url": None,
            "would_contact_payment_provider": False,
            "webhook_endpoint": "/v1/payments/refill-events",
            "event_payload": event_payload if payload.provider == "local" else None,
            "operator_steps": [
                "Collect or confirm the manual buyer deposit outside StormLead.",
                "Post the synthetic local refill event payload only after manual funds are confirmed.",
                "Do not create Stripe Checkout sessions or charge buyers without explicit payment approval.",
            ],
        },
        "buyer": _buyer_wallet_response(buyer),
    }


async def _stripe_wallet_refill_intent_response(
    buyer: BuyerRow,
    payload: WalletRefillIntentRequest,
    decision: Any,
    request: Request,
) -> dict[str, Any]:
    idempotency_key = _refill_idempotency_key(
        buyer_id=buyer.id,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        supplied=payload.idempotency_key,
    )
    session = await _create_stripe_checkout_session(
        buyer=buyer,
        payload=payload,
        idempotency_key=idempotency_key,
        request=request,
    )
    return {
        "buyer_id": str(buyer.id),
        "provider": "stripe",
        "mode": "stripe_sandbox",
        "payment_intent_id": None,
        "amount_cents": payload.amount_cents,
        "currency": payload.currency,
        "status": "requires_stripe_checkout_completion",
        "idempotency_key": idempotency_key,
        "provider_gate": _provider_decision_response(decision),
        "live_payment_approval": _payment_approval_packet(),
        "checkout_contract": {
            "type": "stripe_checkout_session",
            "checkout_session_id": session["id"],
            "live_checkout_url": session["url"],
            "would_contact_payment_provider": True,
            "webhook_endpoint": "/v1/payments/stripe/refill-webhook",
            "event_payload": None,
            "operator_steps": [
                "Complete the Stripe sandbox Checkout Session with a Stripe test card.",
                "Confirm Stripe posts a signed checkout.session.completed webhook to the refill webhook endpoint.",
                "Do not use Stripe live keys unless STORMLEAD_APPROVE_PAYMENTS_LIVE=true is approved.",
            ],
        },
        "buyer": _buyer_wallet_response(buyer),
    }


async def _create_stripe_checkout_session(
    *,
    buyer: BuyerRow,
    payload: WalletRefillIntentRequest,
    idempotency_key: str,
    request: Request,
) -> dict[str, str]:
    secret_key = _stripe_secret_key()
    if not secret_key.startswith("sk_test_"):
        raise _payment_http_exception(
            403,
            "Stripe sandbox checkout requires a sk_test_ secret key",
            "stripe_checkout_requires_sandbox_key",
        )
    origin = str(request.base_url).rstrip("/")
    success_url = os.getenv("STRIPE_CHECKOUT_SUCCESS_URL", f"{origin}/admin?stripe=success")
    cancel_url = os.getenv("STRIPE_CHECKOUT_CANCEL_URL", f"{origin}/admin?stripe=cancel")
    data = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(buyer.id),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": payload.currency.lower(),
        "line_items[0][price_data][unit_amount]": str(payload.amount_cents),
        "line_items[0][price_data][product_data][name]": "StormLead buyer wallet refill",
        "metadata[buyer_id]": str(buyer.id),
        "metadata[idempotency_key]": idempotency_key,
        "metadata[source]": "stormlead_wallet_refill",
    }
    if payload.description:
        data["metadata[description]"] = payload.description[:255]
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data=data,
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Idempotency-Key": idempotency_key,
            },
        )
    if response.status_code >= 400:
        raise _payment_http_exception(
            502,
            "Stripe sandbox checkout session could not be created",
            "stripe_checkout_create_failed",
            stripe_status_code=response.status_code,
        )
    body = response.json()
    session_id = str(body.get("id") or "")
    url = str(body.get("url") or "")
    if not session_id or not url:
        raise _payment_http_exception(
            502,
            "Stripe sandbox checkout response omitted session id or url",
            "stripe_checkout_response_invalid",
        )
    return {"id": session_id, "url": url}


def _stripe_signature_values(header: str) -> tuple[int, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.partition("=")
        if key == "t" and value:
            try:
                timestamp = int(value)
            except ValueError as e:
                raise _payment_http_exception(
                    400,
                    "invalid Stripe webhook timestamp",
                    "stripe_signature_timestamp_invalid",
                ) from e
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        raise _payment_http_exception(
            400,
            "Stripe-Signature must include t and v1 values",
            "stripe_signature_header_invalid",
        )
    return timestamp, signatures


async def _read_stripe_webhook_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as e:
            raise _payment_http_exception(
                400,
                "Stripe webhook Content-Length is invalid",
                "stripe_webhook_content_length_invalid",
            ) from e
        if declared_size > STRIPE_WEBHOOK_MAX_BODY_BYTES:
            raise _payment_http_exception(
                413,
                "Stripe webhook body exceeds the configured size limit",
                "stripe_webhook_body_too_large",
            )

    chunks: list[bytes] = []
    total_size = 0
    async for chunk in request.stream():
        total_size += len(chunk)
        if total_size > STRIPE_WEBHOOK_MAX_BODY_BYTES:
            raise _payment_http_exception(
                413,
                "Stripe webhook body exceeds the configured size limit",
                "stripe_webhook_body_too_large",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _verified_stripe_event(raw_body: bytes, signature_header: str) -> dict[str, Any]:
    secret = _stripe_webhook_secret()
    if not secret.startswith("whsec_"):
        raise _payment_http_exception(
            403,
            "Stripe webhook secret is not configured",
            "stripe_webhook_secret_not_configured",
        )
    timestamp, signatures = _stripe_signature_values(signature_header)
    if abs(int(time.time()) - timestamp) > STRIPE_SIGNATURE_TOLERANCE_SECONDS:
        raise _payment_http_exception(
            400,
            "Stripe webhook timestamp is outside the replay window",
            "stripe_webhook_timestamp_outside_window",
        )
    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise _payment_http_exception(
            400,
            "Stripe webhook signature verification failed",
            "stripe_webhook_signature_invalid",
        )
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise _payment_http_exception(
            400,
            "Stripe webhook body must be valid JSON",
            "stripe_webhook_json_invalid",
        ) from e
    if not isinstance(event, dict):
        raise _payment_http_exception(
            400,
            "Stripe webhook event must be a JSON object",
            "stripe_webhook_event_not_object",
        )
    return event


def _stripe_refill_event_payload(event: Mapping[str, Any]) -> PaymentRefillEventRequest:
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if event.get("livemode") is not False:
        raise _payment_http_exception(
            403,
            "Stripe sandbox refill webhook requires livemode=false",
            "stripe_webhook_livemode_not_allowed",
        )
    data = event.get("data")
    stripe_object_raw = data.get("object") if isinstance(data, Mapping) else None
    if not event_id or not isinstance(stripe_object_raw, Mapping):
        raise _payment_http_exception(
            400,
            "Stripe webhook event is missing id or data.object",
            "stripe_webhook_event_missing_data",
        )
    stripe_object = cast(Mapping[str, Any], stripe_object_raw)
    if event_type not in {"checkout.session.completed", "payment_intent.succeeded"}:
        raise _payment_http_exception(
            409,
            f"Stripe event type {event_type} is not creditable",
            "stripe_webhook_event_not_creditable",
        )
    metadata_raw = stripe_object.get("metadata")
    metadata: Mapping[str, Any]
    if isinstance(metadata_raw, Mapping):
        metadata = cast(Mapping[str, Any], metadata_raw)
    else:
        metadata = {}
    buyer_id = str(metadata.get("buyer_id") or "")
    payment_intent_id = str(stripe_object.get("payment_intent") or stripe_object.get("id") or "")
    amount_cents_raw = stripe_object.get("amount_total") or stripe_object.get("amount_received")
    if amount_cents_raw is None:
        raise _payment_http_exception(
            400,
            "Stripe refill webhook is missing an amount",
            "stripe_webhook_amount_missing",
        )
    currency = str(stripe_object.get("currency") or "usd").upper()
    payment_status = str(stripe_object.get("payment_status") or stripe_object.get("status") or "")
    status = "succeeded" if event_type == "payment_intent.succeeded" else payment_status
    idempotency_key = str(metadata.get("idempotency_key") or f"stripe:{event_id}")
    try:
        return PaymentRefillEventRequest(
            provider="stripe",
            provider_event_id=event_id,
            payment_intent_id=payment_intent_id,
            buyer_id=UUID(buyer_id),
            amount_cents=int(amount_cents_raw),
            currency=currency,
            status=status,
            idempotency_key=idempotency_key,
            metadata={
                "stripe_event_type": event_type,
                "stripe_object_id": str(stripe_object.get("id") or ""),
                "source": str(metadata.get("source") or "stripe_checkout"),
            },
        )
    except (TypeError, ValueError) as e:
        raise _payment_http_exception(
            400,
            "Stripe refill webhook is missing valid refill metadata",
            "stripe_webhook_metadata_invalid",
        ) from e


def _safe_payment_metadata(metadata: Mapping[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in metadata.items():
        normalized_key = str(key).strip()[:64]
        if not normalized_key:
            continue
        lowered = normalized_key.lower()
        if any(keyword in lowered for keyword in PAYMENT_SENSITIVE_METADATA_KEYWORDS):
            safe[normalized_key] = "[redacted]"
            continue
        if isinstance(value, str | int | float | bool) or value is None:
            value_text = "" if value is None else str(value)
        else:
            value_text = json.dumps(value, default=str, sort_keys=True)
        lowered_value = value_text.lower()
        if any(marker in lowered_value for marker in PAYMENT_SENSITIVE_METADATA_VALUE_MARKERS):
            safe[normalized_key] = "[redacted]"
            continue
        safe[normalized_key] = value_text[:512]
    return safe


def _payment_refill_event_audit_payload(
    payload: PaymentRefillEventRequest,
) -> dict[str, Any]:
    return {
        "provider": payload.provider,
        "provider_event_id": payload.provider_event_id,
        "payment_intent_id": payload.payment_intent_id,
        "buyer_id": str(payload.buyer_id),
        "amount_cents": payload.amount_cents,
        "currency": payload.currency,
        "status": payload.status,
        "idempotency_key": payload.idempotency_key,
        "local_simulation": payload.provider == "local",
        "metadata": _safe_payment_metadata(payload.metadata),
    }


def _canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


async def _record_payment_refill_webhook_audit(
    s: Any, payload: PaymentRefillEventRequest, *, status: str
) -> PaymentWebhookEvent:
    audit_payload = _payment_refill_event_audit_payload(payload)
    webhook_event = PaymentWebhookEvent(
        provider=payload.provider,
        external_event_id=payload.provider_event_id,
        event_type=f"wallet.refill.{payload.status}",
        status=status,
        payload_sha256=_canonical_payload_sha256(audit_payload),
        payload_json=audit_payload,
    )
    s.add(webhook_event)
    await s.flush()
    return webhook_event


def _payment_refill_lock_keys(payload: PaymentRefillEventRequest) -> list[str]:
    base = f"wallet-refill:{payload.provider}"
    keys = [
        f"{base}:event:{payload.provider_event_id}",
        f"{base}:intent:{payload.payment_intent_id}",
    ]
    if payload.idempotency_key:
        keys.append(f"{base}:idempotency:{payload.idempotency_key}")
    return sorted(set(keys))


async def _lock_payment_refill_idempotency_scope(
    s: Any, payload: PaymentRefillEventRequest
) -> None:
    lock_statement = text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)")
    for lock_key in _payment_refill_lock_keys(payload):
        await s.execute(lock_statement, {"lock_key": lock_key})


async def _existing_payment_refill_event(
    s: Any,
    *,
    provider: str,
    buyer_id: UUID,
    provider_event_id: str,
    payment_intent_id: str,
    idempotency_key: str | None,
) -> BillingEvent | None:
    duplicate_match = or_(
        BillingEvent.external_event_id == provider_event_id,
        BillingEvent.metadata_json["payment_event_id"].as_string() == provider_event_id,
        BillingEvent.metadata_json["payment_intent_id"].as_string() == payment_intent_id,
    )
    if idempotency_key:
        duplicate_match = or_(
            duplicate_match,
            and_(
                BillingEvent.buyer_id == buyer_id,
                BillingEvent.metadata_json["idempotency_key"].as_string() == idempotency_key,
            ),
        )
    result = await s.execute(
        select(BillingEvent)
        .where(
            BillingEvent.event_type == "deposit.added",
            BillingEvent.metadata_json["payment_provider"].as_string() == provider,
            duplicate_match,
        )
        .order_by(BillingEvent.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def _payment_refill_event_matches(
    existing: BillingEvent, payload: PaymentRefillEventRequest
) -> bool:
    metadata = existing.metadata_json or {}
    return (
        existing.buyer_id == payload.buyer_id
        and existing.amount_cents == payload.amount_cents
        and metadata.get("currency") == payload.currency
        and metadata.get("payment_provider") == payload.provider
        and metadata.get("payment_intent_id") == payload.payment_intent_id
        and (
            metadata.get("payment_event_id") == payload.provider_event_id
            or metadata.get("payment_intent_id") == payload.payment_intent_id
            or (
                payload.idempotency_key is not None
                and metadata.get("idempotency_key") == payload.idempotency_key
            )
        )
    )


def _payment_refill_event_response(
    *,
    buyer: BuyerRow,
    payload: PaymentRefillEventRequest,
    decision: Any,
    billing_event: BillingEvent,
    idempotent_replay: bool,
    webhook_event: PaymentWebhookEvent | None = None,
) -> dict[str, Any]:
    metadata = billing_event.metadata_json or {}
    webhook_event_id = (
        str(webhook_event.id)
        if webhook_event is not None
        else metadata.get("payment_webhook_event_id")
    )
    return {
        "buyer_id": str(buyer.id),
        "provider": payload.provider,
        "provider_event_id": payload.provider_event_id,
        "external_event_id": billing_event.external_event_id,
        "payment_intent_id": payload.payment_intent_id,
        "amount_cents": payload.amount_cents,
        "currency": payload.currency,
        "status": "duplicate_ignored" if idempotent_replay else "credited",
        "idempotent_replay": idempotent_replay,
        "billing_event_id": str(billing_event.id),
        "payment_webhook_event_id": webhook_event_id,
        "payment_webhook_event_status": (
            webhook_event.status
            if webhook_event is not None
            else "processed"
            if webhook_event_id
            else None
        ),
        "provider_gate": _provider_decision_response(decision),
        "buyer": _buyer_wallet_response(buyer),
    }


def _billing_event_summary(event: BillingEvent) -> dict[str, Any]:
    metadata = event.metadata_json or {}
    return {
        "billing_event_id": str(event.id),
        "event_type": event.event_type,
        "amount_cents": event.amount_cents,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "external_event_id": event.external_event_id,
        "payment_provider": metadata.get("payment_provider"),
        "payment_event_id": metadata.get("payment_event_id"),
        "payment_intent_id": metadata.get("payment_intent_id"),
        "source": metadata.get("source"),
    }


def _wallet_reconciliation_payload(
    buyer: BuyerRow,
    *,
    ledger_total_cents: int,
    recent_funding_events: Sequence[BillingEvent],
) -> dict[str, Any]:
    balance_cents = _decimal_to_cents(buyer.deposit_balance)
    delta_cents = balance_cents - ledger_total_cents
    return {
        "buyer": _buyer_wallet_response(buyer),
        "ledger": {
            "signed_total_cents": ledger_total_cents,
            "mutable_balance_cents": balance_cents,
            "delta_cents": delta_cents,
            "reconciled": delta_cents == 0,
            "scope": "billing_events signed amount total compared with buyers.deposit_balance",
            "recent_funding_events": [
                _billing_event_summary(event) for event in recent_funding_events
            ],
        },
        "payment_readiness": {
            "local_refills_ready": True,
            "live_payments_approved": provider_live_approved(ProviderArea.PAYMENTS),
            "approval_packet": _payment_approval_packet(),
        },
    }


def _age_minutes(created_at: datetime | None) -> int:
    if created_at is None:
        return 0
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - created_at).total_seconds() // 60))


def _transition_reason(transition: LeadStateTransition | None) -> str | None:
    if transition is None or not isinstance(transition.payload_json, dict):
        return None
    reason = transition.payload_json.get("reason")
    return str(reason) if reason else None


def _autopilot_exclusion_reasons(
    lead: LeadRow, latest: LeadStateTransition | None, posts: list[PostResult]
) -> list[str]:
    reasons = []
    if not (lead.consent_text or "").strip():
        reasons.append("consent_missing")
    if not (lead.phone_e164 or "").startswith("+"):
        reasons.append("invalid_contact")
    if lead.blocked_for_fraud:
        reasons.append("fraud_signal")
    if set(lead.safety_flags or []) & {
        "power_line",
        "injury",
        "active_danger",
        "roof_impact",
        "structure_impact",
    }:
        reasons.append("safety_review_required")
    if (lead.campaign_source or "").lower() in {
        "google_lsa",
        "local_services_ads",
        "google_local_services_ads",
    }:
        reasons.append("restricted_source_no_resale")
    if lead.hold_for_review or lead.lead_class in {"c", "d"}:
        reasons.append("human_review_required")
    if latest is not None and latest.status not in {"succeeded", "reviewed"}:
        reasons.append("workflow_pending_or_failed")
    if latest is not None and latest.event_type == "lead.unsold":
        reason = _transition_reason(latest)
        if reason in AUTOPILOT_UNSELLABLE_REASONS:
            reasons.append("no_buyer_coverage")
    if any(not post.delivered for post in posts):
        reasons.append("delivery_failure")
    return sorted(set(reasons))


def _buyer_onboarding_readiness(buyer: BuyerRow) -> dict[str, Any]:
    return buyer_activation_readiness(buyer)


def _buyer_sandbox_certification_response(buyer: BuyerRow) -> dict[str, Any]:
    readiness = _buyer_onboarding_readiness(buyer)
    required = (
        "service_ready",
        "zip_ready",
        "pricing_ready",
        "webhook_ready",
        "api_key_ready",
    )
    missing = [name for name in required if not readiness.get(name)]
    return {
        "buyer_id": str(buyer.id),
        "mode": "local_sandbox_only",
        "certification_ready": not missing,
        "missing_requirements": missing,
        "would_contact_buyer": False,
        "endpoint_under_test": buyer.webhook_url,
        "local_execution_note": (
            "This contract is dry-run evidence only; real buyer webhook calls remain "
            "approval-gated until a specific buyer endpoint and synthetic certification action "
            "are explicitly approved."
        ),
        "request_contract": {
            "ping": {
                "method": "POST",
                "mode_header": "X-Stormlead-Mode: ping",
                "content_type": "application/json",
                "timeout_seconds": PING_TIMEOUT_S,
                "body_fields": [
                    "lead_id",
                    "state",
                    "zip",
                    "requested_service",
                    "damage_tier",
                    "damage_type",
                    "urgency",
                    "damage_summary",
                    "visible_risk_level",
                    "estimated_job_size",
                    "buyer_notes",
                    "avm_band",
                ],
                "expected_response": {
                    "accept": "boolean",
                    "bid_cents": "positive integer when accept=true",
                },
            },
            "post": {
                "method": "POST",
                "mode_header": "X-Stormlead-Mode: post",
                "content_type": "application/json",
                "timeout_seconds": POST_TIMEOUT_S,
                "body_sections": ["lead", "address", "consent", "purchase"],
                "required_headers": ["Idempotency-Key"],
                "success_status_codes": "2xx",
                "pii_boundary": "PII is sent only after the buyer wins and delivery is approved.",
            },
        },
        "auth_contract": {
            "scheme": "StormLead HMAC-SHA256",
            "signed_headers": ["Webhook-Timestamp", "Webhook-Signature", "Webhook-Id"],
            "secret_source": "buyer.webhook_secret",
        },
        "retry_policy": {
            "retry_on_status_codes": [429, "5xx"],
            "retry_on_errors": ["timeout", "network_error"],
            "max_attempts": POST_MAX_ATTEMPTS,
            "base_delay_seconds": POST_RETRY_BASE_DELAY_S,
        },
        "activation_dependency": {
            "must_pass_before_active_delivery": True,
            "activation_readiness": readiness,
        },
    }


def _buyer_coverage_zips(buyer: BuyerRow) -> list[str]:
    return _normalize_string_list(list((buyer.target_zips or []) + (buyer.exclusive_zips or [])))


def _zip_looks_louisiana(zip_code: str) -> bool:
    return zip_code.startswith("70") or zip_code.startswith("71")


def _buyer_manual_delivery_ready(buyer: BuyerRow) -> bool:
    notes = str(buyer.notes or "").lower()
    return "manual delivery approved" in notes or "approved manual delivery" in notes


def _single_buyer_canary_readiness(
    buyer: BuyerRow,
    *,
    market_state: str,
    market_zip: str | None,
    service: str,
    monthly_budget_cents: int,
) -> dict[str, Any]:
    activation = _buyer_onboarding_readiness(buyer)
    coverage_zips = sorted(_buyer_coverage_zips(buyer))
    services = _normalize_string_list(list(buyer.services or []))
    balance_cents = _decimal_to_cents(buyer.deposit_balance)
    monthly_budget_ready = _decimal_to_cents(buyer.monthly_budget) >= monthly_budget_cents
    wallet_ready = balance_cents >= monthly_budget_cents and balance_cents > 0
    service_ready = service in services
    if market_zip:
        zip_ready = market_zip in coverage_zips
    else:
        zip_ready = bool(set(coverage_zips) & LOUISIANA_CANARY_ZIPS) or any(
            _zip_looks_louisiana(zip_code) for zip_code in coverage_zips
        )
    delivery_path_ready = bool(
        buyer.webhook_url and buyer.webhook_secret and buyer.api_key
    ) or _buyer_manual_delivery_ready(buyer)
    terms_ready = (
        str(buyer.sales_stage or "") == BuyerSalesStage.FUNDED.value
        or "terms accepted" in str(buyer.notes or "").lower()
    )
    requirements = {
        "active_status": buyer.status == BuyerStatus.ACTIVE.value,
        "terms_or_manual_delivery_policy_ready": terms_ready,
        "service_tree_removal_ready": service_ready,
        "louisiana_zip_coverage_ready": market_state == "LA" and zip_ready,
        "wallet_covers_monthly_ad_budget": wallet_ready,
        "lead_price_ready": _decimal_to_cents(buyer.bid_per_lead_t1_t2) > 0
        and _decimal_to_cents(buyer.bid_per_lead_t3) > 0,
        "caps_and_budget_ready": int(buyer.daily_cap or 0) > 0 and monthly_budget_ready,
        "delivery_path_ready": delivery_path_ready,
    }
    missing = [name for name, ready in requirements.items() if not ready]
    return {
        "buyer_id": str(buyer.id),
        "company": buyer.company,
        "canary_ready": not missing,
        "missing_requirements": missing,
        "requirements": requirements,
        "coverage_zips": coverage_zips,
        "services": services,
        "delivery_mode": "manual_approved"
        if _buyer_manual_delivery_ready(buyer)
        else "webhook"
        if delivery_path_ready
        else "missing",
        "activation_readiness": activation,
        "wallet_balance_cents": balance_cents,
        "monthly_budget_cents": _decimal_to_cents(buyer.monthly_budget),
        "daily_cap": buyer.daily_cap,
    }


@app.get("/v1/admin/canary-readiness")
async def single_buyer_canary_readiness(
    market_state: str = Query(default=DEFAULT_CANARY_MARKET_STATE, min_length=2, max_length=2),
    market_zip: str | None = Query(default=None, min_length=3, max_length=10),
    service: str = Query(default=DEFAULT_CANARY_SERVICE, min_length=1, max_length=64),
    monthly_budget_cents: int = Query(default=DEFAULT_CANARY_MONTHLY_BUDGET_CENTS, ge=0),
    daily_budget_cents: int = Query(default=DEFAULT_CANARY_DAILY_BUDGET_CENTS, ge=0),
    require_sold_evidence: bool = Query(default=False),
) -> dict[str, Any]:
    """Evaluate the narrowed Louisiana one-buyer paid canary without changing full launch gates."""
    normalized_state = market_state.strip().upper()
    normalized_service = service.strip().lower()
    if normalized_state != DEFAULT_CANARY_MARKET_STATE:
        raise HTTPException(400, "single-buyer paid canary is currently scoped to Louisiana only")
    lead_scope = [
        LeadRow.state == normalized_state,
        LeadRow.requested_service == normalized_service,
    ]
    if market_zip:
        lead_scope.append(LeadRow.zip == market_zip)
    try:
        async with get_session() as s:
            buyers = (
                (
                    await s.execute(
                        select(BuyerRow).where(
                            BuyerRow.status == BuyerStatus.ACTIVE.value,
                            BuyerRow.services.contains([normalized_service]),
                        )
                    )
                )
                .scalars()
                .all()
            )
            lead_ids_subq = select(LeadRow.id).where(and_(*lead_scope)).subquery()
            delivered = await s.scalar(
                select(func.count(PostResult.id)).where(
                    PostResult.delivered.is_(True),
                    PostResult.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            attributed_leads = await s.scalar(
                select(func.count(LeadRow.id)).where(
                    LeadRow.id.in_(select(lead_ids_subq.c.id)),
                    or_(
                        and_(LeadRow.google_click_id.is_not(None), LeadRow.google_click_id != ""),
                        and_(LeadRow.campaign_source.is_not(None), LeadRow.campaign_source != ""),
                    ),
                )
            )
            failed_deliveries = await s.scalar(
                select(func.count(PostResult.id)).where(
                    PostResult.delivered.is_(False),
                    PostResult.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
    except Exception as e:
        log.error("admin.canary_readiness_failed", error=str(e))
        raise HTTPException(
            500, "canary readiness could not be computed; retry after checking database health"
        ) from e

    buyer_readiness = [
        _single_buyer_canary_readiness(
            buyer,
            market_state=normalized_state,
            market_zip=market_zip,
            service=normalized_service,
            monthly_budget_cents=monthly_budget_cents,
        )
        for buyer in buyers
    ]
    eligible_buyers = [item for item in buyer_readiness if item["canary_ready"]]
    daily_budget_within_monthly_cap = daily_budget_cents * 30 <= monthly_budget_cents
    payment_gate = _stripe_sandbox_payment_decision("prepare Stripe sandbox buyer wallet refill")
    ads_dry_run_gate = provider_decision(
        ProviderArea.ADS, action="prepare Google Ads dry-run canary"
    )
    buyer_delivery_gate = provider_decision(
        ProviderArea.BUYER_DELIVERY, action="prepare one-buyer canary delivery"
    )
    checks = {
        "one_active_louisiana_buyer_ready": len(eligible_buyers) >= 1,
        "stripe_sandbox_ready": payment_gate.allowed,
        "ads_dry_run_allowed": ads_dry_run_gate.allowed,
        "buyer_delivery_gate_not_paused": buyer_delivery_gate.allowed,
        "campaign_daily_budget_within_monthly_cap": daily_budget_within_monthly_cap,
        "synthetic_sold_lead_evidence_present": int(delivered or 0) > 0
        or not require_sold_evidence,
        "attribution_evidence_present": int(attributed_leads or 0) > 0 or not require_sold_evidence,
    }
    technical_ready = all(checks.values())
    ready_for_real_ads = technical_ready and provider_live_approved(ProviderArea.ADS)
    return {
        "mode": "single_buyer_paid_canary",
        "scope": {
            "market_state": normalized_state,
            "market_zip": market_zip,
            "service": normalized_service,
            "monthly_budget_cents": monthly_budget_cents,
            "daily_budget_cents": daily_budget_cents,
            "default_louisiana_canary_zips": sorted(LOUISIANA_CANARY_ZIPS),
        },
        "readiness_label": "single_buyer_paid_canary_ready"
        if technical_ready
        else "single_buyer_paid_canary_blocked",
        "technical_canary_ready": technical_ready,
        "ready_for_real_ads": ready_for_real_ads,
        "ready_for_paid_launch": False,
        "full_launch_gate_note": "The existing /v1/admin/launch-readiness three-buyer paid-pilot gate is unchanged.",
        "checks": checks,
        "provider_gate": {
            "payments_sandbox": _provider_decision_response(payment_gate),
            "ads_dry_run": _provider_decision_response(ads_dry_run_gate),
            "buyer_delivery": _provider_decision_response(buyer_delivery_gate),
            "ads_live_approved": provider_live_approved(ProviderArea.ADS),
            "payments_live_approved": provider_live_approved(ProviderArea.PAYMENTS),
        },
        "metrics": {
            "candidate_buyers": len(buyer_readiness),
            "eligible_buyers": len(eligible_buyers),
            "delivered_posts": int(delivered or 0),
            "failed_deliveries": int(failed_deliveries or 0),
            "attributed_leads": int(attributed_leads or 0),
        },
        "buyer_readiness": buyer_readiness,
        "recommended_next_actions": [
            "Add one funded Louisiana buyer with service zips and delivery path."
            if len(eligible_buyers) < 1
            else "Run one synthetic Louisiana lead through capture, sale, wallet debit, and buyer report.",
            "Set STORMLEAD_APPROVE_PAYMENTS_SANDBOX=true with sk_test_/whsec_ secrets to test Stripe sandbox."
            if not payment_gate.allowed
            else "Complete Stripe sandbox Checkout and verify signed webhook wallet credit.",
            "Keep Google Ads paused until explicit spend approval; use offline conversion dry-run first.",
        ],
    }


def _exception_item(
    *,
    exception_id: str,
    kind: str,
    severity: str,
    reason: str,
    entity_type: str,
    created_at: datetime | None,
    recommended_action: str,
    lead: LeadRow | None = None,
    buyer: BuyerRow | None = None,
    return_request: ReturnRequest | None = None,
    post: PostResult | None = None,
    actions: list[str] | None = None,
) -> dict[str, Any]:
    market = None
    service = None
    if lead is not None:
        market = f"{lead.state}-{lead.zip}"
        service = lead.requested_service
    return {
        "exception_id": exception_id,
        "kind": kind,
        "severity": severity,
        "reason": reason,
        "entity_type": entity_type,
        "lead_id": str(lead.id) if lead is not None else str(post.lead_id) if post else None,
        "buyer_id": str(buyer.id) if buyer is not None else str(post.buyer_id) if post else None,
        "return_request_id": str(return_request.id) if return_request is not None else None,
        "post_result_id": str(post.id) if post is not None else None,
        "market": market,
        "service": service,
        "created_at": created_at.isoformat() if created_at else None,
        "sla_age_minutes": _age_minutes(created_at),
        "recommended_action": recommended_action,
        "actions": actions or [],
    }


def _post_result_looks_like_timeout(post: PostResult) -> bool:
    if post.response_status_code is None:
        return True
    response_body = (post.response_body or "").lower()
    return "timeout" in response_body or "timed out" in response_body


def _buyer_timeout_cluster_exception_items(
    failed_posts: Sequence[PostResult], *, now: datetime | None = None
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(UTC)
    cutoff = current_time - BUYER_TIMEOUT_CLUSTER_WINDOW
    by_buyer: dict[UUID, list[PostResult]] = {}
    for post in failed_posts:
        created_at = _datetime_as_utc(post.created_at)
        if created_at is None or created_at < cutoff or not _post_result_looks_like_timeout(post):
            continue
        by_buyer.setdefault(post.buyer_id, []).append(post)

    items: list[dict[str, Any]] = []
    for buyer_id, posts in by_buyer.items():
        if len(posts) < BUYER_TIMEOUT_CLUSTER_MIN_FAILURES:
            continue
        created_candidates = [_datetime_as_utc(post.created_at) for post in posts]
        created_values = [value for value in created_candidates if value is not None]
        first_seen = min(created_values) if created_values else current_time
        latest_seen = max(created_values) if created_values else current_time
        items.append(
            {
                "exception_id": f"buyer:{buyer_id}:timeout_cluster",
                "kind": "buyer_timeout_cluster",
                "severity": "critical",
                "reason": "buyer_timeout_cluster",
                "entity_type": "buyer",
                "lead_id": None,
                "buyer_id": str(buyer_id),
                "return_request_id": None,
                "post_result_id": None,
                "market": None,
                "service": None,
                "created_at": first_seen.isoformat(),
                "sla_age_minutes": _age_minutes(first_seen),
                "recommended_action": (
                    f"Investigate {len(posts)} timeout-like post failures for this buyer "
                    f"between {first_seen.isoformat()} and {latest_seen.isoformat()}; "
                    "pause or reroute only after confirming local-only delivery safety."
                ),
                "actions": [],
            }
        )
    return items


def _parse_exception_created_at(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _exception_uuid(value: Any) -> UUID | None:
    if value in {None, ""}:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _exception_queue_sla_due_at(item: Mapping[str, Any], now: datetime) -> datetime:
    created_at = _parse_exception_created_at(item.get("created_at")) or now
    severity = str(item.get("severity") or "warning")
    return created_at + EXCEPTION_SLA_BY_SEVERITY.get(severity, timedelta(hours=24))


def _exception_queue_payload(item: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "source": "computed_admin_autopilot_exceptions",
        "source_exception_id": str(item["exception_id"]),
        "policy_version": AUTOPILOT_POLICY_VERSION,
        "synced_at": now.isoformat(),
        "market": item.get("market"),
        "service": item.get("service"),
        "actions": item.get("actions") or [],
        "sla_age_minutes": item.get("sla_age_minutes"),
    }


def _new_exception_queue_item(item: Mapping[str, Any], *, now: datetime) -> ExceptionQueueItem:
    kind = str(item["kind"])
    return ExceptionQueueItem(
        kind=kind,
        severity=str(item["severity"]),
        status="open",
        owner=EXCEPTION_OWNER_BY_KIND.get(kind, "ops-oncall"),
        entity_type=str(item["entity_type"]),
        lead_id=_exception_uuid(item.get("lead_id")),
        buyer_id=_exception_uuid(item.get("buyer_id")),
        return_request_id=_exception_uuid(item.get("return_request_id")),
        post_result_id=_exception_uuid(item.get("post_result_id")),
        reason=str(item["reason"]),
        recommended_action=str(item["recommended_action"]),
        idempotency_key=str(item["exception_id"]),
        sla_due_at=_exception_queue_sla_due_at(item, now),
        payload_json=_exception_queue_payload(item, now),
    )


def _refresh_exception_queue_item(
    row: ExceptionQueueItem, item: Mapping[str, Any], *, now: datetime
) -> None:
    kind = str(item["kind"])
    row.kind = kind
    row.severity = str(item["severity"])
    row.owner = EXCEPTION_OWNER_BY_KIND.get(kind, row.owner or "ops-oncall")
    row.entity_type = str(item["entity_type"])
    row.lead_id = _exception_uuid(item.get("lead_id"))
    row.buyer_id = _exception_uuid(item.get("buyer_id"))
    row.return_request_id = _exception_uuid(item.get("return_request_id"))
    row.post_result_id = _exception_uuid(item.get("post_result_id"))
    row.reason = str(item["reason"])
    row.recommended_action = str(item["recommended_action"])
    row.sla_due_at = _exception_queue_sla_due_at(item, now)
    row.payload_json = _exception_queue_payload(item, now)
    row.updated_at = now


async def _sync_exception_queue_items(
    s: Any, items: Sequence[Mapping[str, Any]], *, now: datetime | None = None
) -> dict[str, int]:
    sync_now = now or datetime.now(UTC)
    summary = {
        "inserted": 0,
        "updated": 0,
        "skipped_closed": 0,
        "computed": len(items),
    }
    for item in items:
        idempotency_key = str(item["exception_id"])
        existing = (
            (
                await s.execute(
                    select(ExceptionQueueItem)
                    .where(ExceptionQueueItem.idempotency_key == idempotency_key)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            s.add(_new_exception_queue_item(item, now=sync_now))
            summary["inserted"] += 1
            continue
        if existing.status in {"resolved", "dismissed"}:
            summary["skipped_closed"] += 1
            continue
        _refresh_exception_queue_item(existing, item, now=sync_now)
        summary["updated"] += 1
    if summary["inserted"] or summary["updated"]:
        await s.flush()
    return summary


def _increment_count(counts: dict[str, int], key: str | None) -> None:
    normalized = (key or "unassigned").strip() or "unassigned"
    counts[normalized] = counts.get(normalized, 0) + 1


def _datetime_as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _exception_queue_dashboard_summary(
    rows: Sequence[ExceptionQueueItem], *, now: datetime | None = None
) -> dict[str, Any]:
    current_time = now or datetime.now(UTC)
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    by_area: dict[str, int] = {}
    oldest_sla_due_at: datetime | None = None
    overdue_count = 0
    active_rows = [row for row in rows if row.status in ACTIVE_EXCEPTION_QUEUE_STATUSES]
    for row in active_rows:
        kind = str(row.kind)
        sla_due_at = _datetime_as_utc(row.sla_due_at)
        _increment_count(by_status, str(row.status))
        _increment_count(by_severity, str(row.severity))
        _increment_count(by_owner, row.owner)
        _increment_count(by_kind, kind)
        _increment_count(by_area, EXCEPTION_DASHBOARD_AREA_BY_KIND.get(kind, "operations"))
        if sla_due_at is not None:
            if oldest_sla_due_at is None or sla_due_at < oldest_sla_due_at:
                oldest_sla_due_at = sla_due_at
            if sla_due_at <= current_time:
                overdue_count += 1
    return {
        "schema_version": 1,
        "policy_version": AUTOPILOT_POLICY_VERSION,
        "source": "exception_queue",
        "mode": "local_read_only",
        "would_contact_provider": False,
        "pii_redacted": True,
        "active_count": len(active_rows),
        "overdue_count": overdue_count,
        "oldest_sla_due_at": oldest_sla_due_at.isoformat() if oldest_sla_due_at else None,
        "by_status": by_status,
        "by_severity": by_severity,
        "by_owner": by_owner,
        "by_kind": by_kind,
        "by_area": by_area,
    }


def _budget_json_subset(payload: object, keys: Sequence[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    return {key: payload.get(key) for key in keys if key in payload}


def _budget_decision_flag(payload: object, key: str) -> bool:
    if not isinstance(payload, Mapping):
        return False
    return payload.get(key) is True


def _budget_action_summary_item(row: BudgetActionLog) -> dict[str, Any]:
    created_at = _datetime_as_utc(row.created_at)
    metrics = _budget_json_subset(
        row.metrics_json,
        [
            "current_daily_budget_cents",
            "proposed_daily_budget_cents",
            "spend_cents",
            "qualified_leads",
            "cpl_cents",
            "roas",
            "sample_ready",
            "cooldown_active",
        ],
    )
    decision = _budget_json_subset(
        row.decision_json,
        [
            "evaluation_date",
            "max_daily_budget_cents",
            "max_cpl_cents",
            "min_roas",
            "would_contact_ads_provider",
            "would_mutate_ads_provider",
            "would_spend_money",
            "approval_required_before_live_ads_action",
        ],
    )
    return {
        "id": str(row.id),
        "campaign_id": str(row.campaign_id),
        "platform": row.platform,
        "external_campaign_id": row.external_campaign_id,
        "action": row.action,
        "status": row.status,
        "approval_required": bool(row.approval_required),
        "reason": row.reason,
        "created_at": created_at.isoformat() if created_at else None,
        "metrics": metrics,
        "decision": decision,
        "safety": {
            "would_contact_ads_provider": _budget_decision_flag(
                row.decision_json, "would_contact_ads_provider"
            ),
            "would_mutate_ads_provider": _budget_decision_flag(
                row.decision_json, "would_mutate_ads_provider"
            ),
            "would_spend_money": _budget_decision_flag(row.decision_json, "would_spend_money"),
        },
    }


def _budget_action_dashboard_summary(
    rows: Sequence[BudgetActionLog], *, recent_limit: int = 25
) -> dict[str, Any]:
    active_rows = [row for row in rows if row.status in ACTIVE_BUDGET_ACTION_STATUSES]
    by_action: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_platform: dict[str, int] = {}
    approval_required_count = 0
    rows_with_provider_contact_intent = 0
    rows_with_provider_mutation_intent = 0
    rows_with_spend_intent = 0
    for row in active_rows:
        _increment_count(by_action, row.action)
        _increment_count(by_status, row.status)
        _increment_count(by_platform, row.platform)
        if row.approval_required or row.status == "approval_required":
            approval_required_count += 1
        rows_with_provider_contact_intent += int(
            _budget_decision_flag(row.decision_json, "would_contact_ads_provider")
        )
        rows_with_provider_mutation_intent += int(
            _budget_decision_flag(row.decision_json, "would_mutate_ads_provider")
        )
        rows_with_spend_intent += int(_budget_decision_flag(row.decision_json, "would_spend_money"))

    return {
        "schema_version": 1,
        "policy_version": AUTOPILOT_POLICY_VERSION,
        "source": "budget_action_logs",
        "mode": "local_read_only",
        "endpoint_would_contact_ads_provider": False,
        "endpoint_would_mutate_ads_provider": False,
        "endpoint_would_spend_money": False,
        "rows_with_provider_contact_intent": rows_with_provider_contact_intent,
        "rows_with_provider_mutation_intent": rows_with_provider_mutation_intent,
        "rows_with_spend_intent": rows_with_spend_intent,
        "active_count": len(active_rows),
        "approval_required_count": approval_required_count,
        "auto_pause_count": by_action.get("auto_pause", 0),
        "blocked_count": by_action.get("block_increase", 0),
        "by_action": by_action,
        "by_status": by_status,
        "by_platform": by_platform,
        "recent_actions": [_budget_action_summary_item(row) for row in active_rows[:recent_limit]],
        "operator_note": (
            "Budget actions are read-only local audit rows. Provider changes and budget "
            "increases require explicit approval outside this dashboard."
        ),
    }


def _learning_json_subset(payload: object, keys: Sequence[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    return {key: payload.get(key) for key in keys if key in payload}


def _learning_proposal_summary_item(row: LearningProposal) -> dict[str, Any]:
    created_at = _datetime_as_utc(row.created_at)
    updated_at = _datetime_as_utc(row.updated_at)
    return {
        "id": str(row.id),
        "source_proposal_id": str(row.source_proposal_id) if row.source_proposal_id else None,
        "proposal_date": row.proposal_date.isoformat(),
        "proposal_type": row.proposal_type,
        "target_area": row.target_area,
        "title": row.title,
        "status": row.status,
        "canary_percent": int(row.canary_percent or 0),
        "approval_required": bool(row.approval_required),
        "rollback_reason": row.rollback_reason,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "guardrail": {
            "metric": row.guardrail_metric,
            "baseline_value": row.baseline_value,
            "candidate_value": row.candidate_value,
            "rollback_threshold_pct": row.rollback_threshold_pct,
        },
        "proposal": _learning_json_subset(
            row.proposal_json,
            [
                "confidence",
                "expected_impact",
                "metric",
                "proposal_type",
                "skill_name",
                "target_area",
            ],
        ),
        "replay_result": _learning_json_subset(
            row.replay_result_json,
            [
                "status",
                "canary_percent",
                "approval_required",
                "rollback_required",
                "reason",
                "guardrail_metric",
                "baseline_rate",
                "candidate_rate",
                "relative_drop_pct",
            ],
        ),
        "safety": {
            "would_route_live_traffic": False,
            "would_promote_without_admin_approval": False,
            "requires_admin_approval_for_full_rollout": bool(
                row.approval_required or row.status == "pending_approval"
            ),
        },
    }


def _learning_proposal_dashboard_summary(
    rows: Sequence[LearningProposal], *, recent_limit: int = 25
) -> dict[str, Any]:
    active_rows = [row for row in rows if row.status in ACTIVE_LEARNING_PROPOSAL_STATUSES]
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_target_area: dict[str, int] = {}
    by_guardrail_metric: dict[str, int] = {}
    approval_required_count = 0
    rows_with_full_rollout_intent = 0
    max_canary_percent = 0
    for row in active_rows:
        canary_percent = int(row.canary_percent or 0)
        max_canary_percent = max(max_canary_percent, canary_percent)
        _increment_count(by_status, row.status)
        _increment_count(by_type, row.proposal_type)
        _increment_count(by_target_area, row.target_area)
        _increment_count(by_guardrail_metric, row.guardrail_metric)
        if row.approval_required or row.status == "pending_approval":
            approval_required_count += 1
        if canary_percent >= 100:
            rows_with_full_rollout_intent += 1

    return {
        "schema_version": 1,
        "policy_version": AUTOPILOT_POLICY_VERSION,
        "source": "learning_proposals",
        "mode": "local_read_only",
        "endpoint_would_route_live_traffic": False,
        "endpoint_would_promote_proposal": False,
        "endpoint_would_contact_provider": False,
        "endpoint_requires_admin_approval_for_full_rollout": True,
        "rows_with_full_rollout_intent": rows_with_full_rollout_intent,
        "active_count": len(active_rows),
        "pending_replay_count": by_status.get("pending_replay", 0),
        "canary_active_count": by_status.get("canary_active", 0),
        "rollback_count": by_status.get("rollback_triggered", 0),
        "pending_approval_count": by_status.get("pending_approval", 0),
        "approval_required_count": approval_required_count,
        "max_canary_percent": max_canary_percent,
        "by_status": by_status,
        "by_type": by_type,
        "by_target_area": by_target_area,
        "by_guardrail_metric": by_guardrail_metric,
        "recent_proposals": [
            _learning_proposal_summary_item(row) for row in active_rows[:recent_limit]
        ],
        "operator_note": (
            "Learning proposals are read-only local replay/canary rows. Full rollout, "
            "live traffic routing, and proposal promotion require explicit admin approval."
        ),
    }


async def _build_autopilot_exceptions(
    s: Any,
    *,
    limit: int = 50,
    kind: str | None = None,
    lead_id: UUID | None = None,
    buyer_id: UUID | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def include(item: dict[str, Any]) -> None:
        if kind is not None and item["kind"] != kind:
            return
        if lead_id is not None and item.get("lead_id") != str(lead_id):
            return
        if buyer_id is not None and item.get("buyer_id") != str(buyer_id):
            return
        items.append(item)

    if kind is None or kind == "return_pending":
        return_query = select(ReturnRequest).where(
            ReturnRequest.status.in_(ACTIVE_RETURN_REQUEST_STATUSES)
        )
        if lead_id is not None:
            return_query = return_query.where(ReturnRequest.lead_id == lead_id)
        if buyer_id is not None:
            return_query = return_query.where(ReturnRequest.buyer_id == buyer_id)
        active_returns = (
            (await s.execute(return_query.order_by(ReturnRequest.created_at.asc()).limit(limit)))
            .scalars()
            .all()
        )
        for request in active_returns:
            lead = await s.get(LeadRow, request.lead_id)
            buyer = await s.get(BuyerRow, request.buyer_id)
            include(
                _exception_item(
                    exception_id=f"return:{request.id}",
                    kind="return_pending",
                    severity="warning",
                    reason=request.reason,
                    entity_type="return_request",
                    created_at=request.created_at,
                    recommended_action="Approve, reject, or hold the buyer return request from policy evidence.",
                    lead=lead,
                    buyer=buyer,
                    return_request=request,
                    actions=["approve_return", "reject_return"],
                )
            )

    if (kind is None or kind == "lead_review") and buyer_id is None:
        held_query = select(LeadRow).where(
            (LeadRow.hold_for_review.is_(True)) | (LeadRow.blocked_for_fraud.is_(True))
        )
        if lead_id is not None:
            held_query = held_query.where(LeadRow.id == lead_id)
        held_leads = (
            (await s.execute(held_query.order_by(LeadRow.updated_at.asc()).limit(limit)))
            .scalars()
            .all()
        )
        for lead in held_leads:
            reason = "fraud_signal" if lead.blocked_for_fraud else "human_review_required"
            actions = (
                ["open_timeline"] if lead.blocked_for_fraud else ["open_timeline", "approve_lead"]
            )
            include(
                _exception_item(
                    exception_id=f"lead:{lead.id}:review",
                    kind="lead_review",
                    severity="critical" if lead.blocked_for_fraud else "warning",
                    reason=reason,
                    entity_type="lead",
                    created_at=lead.updated_at or lead.created_at,
                    recommended_action="Open the timeline and approve only if consent, quality, and fraud checks are acceptable.",
                    lead=lead,
                    actions=actions,
                )
            )

    if kind is None or kind in {"delivery_failure", "buyer_timeout_cluster"}:
        failed_post_query = select(PostResult).where(PostResult.delivered.is_(False))
        if lead_id is not None:
            failed_post_query = failed_post_query.where(PostResult.lead_id == lead_id)
        if buyer_id is not None:
            failed_post_query = failed_post_query.where(PostResult.buyer_id == buyer_id)
        failed_posts = (
            (await s.execute(failed_post_query.order_by(PostResult.created_at.asc()).limit(limit)))
            .scalars()
            .all()
        )
        if kind is None or kind == "delivery_failure":
            for post in failed_posts:
                lead = await s.get(LeadRow, post.lead_id)
                buyer = await s.get(BuyerRow, post.buyer_id)
                include(
                    _exception_item(
                        exception_id=f"post:{post.id}:delivery",
                        kind="delivery_failure",
                        severity="critical",
                        reason="post_failed",
                        entity_type="post_result",
                        created_at=post.created_at,
                        recommended_action="Check buyer webhook health and reroute only after confirming local-only delivery safety.",
                        lead=lead,
                        buyer=buyer,
                        post=post,
                        actions=["open_timeline"],
                    )
                )
        if (kind is None or kind == "buyer_timeout_cluster") and lead_id is None:
            for item in _buyer_timeout_cluster_exception_items(failed_posts):
                include(item)

    if (kind is None or kind == "no_buyer_coverage") and buyer_id is None:
        unsold_query = select(LeadStateTransition).where(
            LeadStateTransition.event_type == "lead.unsold"
        )
        if lead_id is not None:
            unsold_query = unsold_query.where(LeadStateTransition.lead_id == lead_id)
        unsold_rows = (
            (
                await s.execute(
                    unsold_query.order_by(LeadStateTransition.created_at.desc()).limit(limit * 3)
                )
            )
            .scalars()
            .all()
        )
        seen_unsold: set[UUID] = set()
        for transition in unsold_rows:
            if transition.lead_id in seen_unsold:
                continue
            transition_reason = _transition_reason(transition)
            if transition_reason not in AUTOPILOT_UNSELLABLE_REASONS:
                continue
            lead = await s.get(LeadRow, transition.lead_id)
            if lead is None or lead.status in AUTOPILOT_SUCCESS_STATES:
                continue
            seen_unsold.add(transition.lead_id)
            include(
                _exception_item(
                    exception_id=f"lead:{lead.id}:coverage",
                    kind="no_buyer_coverage",
                    severity="warning",
                    reason=transition_reason or "no_buyer_coverage",
                    entity_type="lead",
                    created_at=transition.created_at,
                    recommended_action="Add or fund a buyer covering this market/service before retrying auction.",
                    lead=lead,
                    actions=["open_timeline"],
                )
            )

    buyer_exception_kinds = {"buyer_wallet_low", "buyer_onboarding_incomplete"}
    if (kind is None or kind in buyer_exception_kinds) and lead_id is None:
        buyer_query = select(BuyerRow)
        if buyer_id is not None:
            buyer_query = buyer_query.where(BuyerRow.id == buyer_id)
        buyers = (await s.execute(buyer_query.order_by(BuyerRow.updated_at.asc()))).scalars().all()
        for buyer in buyers:
            readiness = _buyer_onboarding_readiness(buyer)
            if readiness["autopilot_ready"]:
                continue
            if buyer.status == BuyerStatus.ACTIVE.value and readiness["auto_pause_recommended"]:
                include(
                    _exception_item(
                        exception_id=f"buyer:{buyer.id}:wallet",
                        kind="buyer_wallet_low",
                        severity="warning",
                        reason="wallet_below_threshold",
                        entity_type="buyer",
                        created_at=buyer.updated_at or buyer.created_at,
                        recommended_action="Collect or simulate wallet funding, then resume routing for this buyer.",
                        buyer=buyer,
                        actions=[],
                    )
                )
            elif buyer.status in {
                BuyerStatus.ACTIVE.value,
                BuyerStatus.PENDING_VERIFICATION.value,
                BuyerStatus.PAUSED.value,
            }:
                include(
                    _exception_item(
                        exception_id=f"buyer:{buyer.id}:onboarding",
                        kind="buyer_onboarding_incomplete",
                        severity="info",
                        reason="buyer_not_autopilot_ready",
                        entity_type="buyer",
                        created_at=buyer.updated_at or buyer.created_at,
                        recommended_action="Complete terms, service/zip coverage, wallet, budget, API key, and webhook readiness before activation.",
                        buyer=buyer,
                        actions=[],
                    )
                )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    items.sort(
        key=lambda item: (
            severity_rank.get(str(item["severity"]), 9),
            -int(item["sla_age_minutes"]),
            str(item["exception_id"]),
        )
    )
    return items[:limit]


async def _apply_return_decision(
    s: Any,
    request: ReturnRequest,
    result: PostResult,
    buyer: BuyerRow,
    *,
    action: str,
    operator: str,
    notes: str | None,
    task_name: str,
    policy_version: str | None = None,
) -> dict[str, Any]:
    request.reviewed_by = operator
    request.review_notes = notes
    request.reviewed_at = datetime.now(UTC)
    credited_cents = 0
    event_type = f"lead.return_{action}ed"
    if action == "hold":
        request.status = "held"
        event_type = "lead.return_held"
    elif action == "reject":
        request.status = "rejected"
    else:
        event_type = "lead.return_approved"
        if result.returned:
            raise HTTPException(409, "lead sale has already been credited")
        credit = Decimal(result.bid_cents) / Decimal(100)
        buyer.deposit_balance += credit
        buyer.lifetime_spend -= credit
        result.returned = True
        result.return_reason = request.reason
        request.status = "approved"
        credited_cents = result.bid_cents
        s.add(
            BillingEvent(
                buyer_id=request.buyer_id,
                lead_id=request.lead_id,
                event_type="lead.returned",
                amount_cents=result.bid_cents,
                metadata_json={
                    "return_request_id": str(request.id),
                    "post_result_id": str(result.id),
                    "reason": request.reason,
                    "notes_present": bool(request.notes),
                    "review_notes_present": bool(notes),
                    "operator": operator,
                    "policy_version": policy_version,
                },
            )
        )

    current_state = await latest_state(s, request.lead_id) or PipelineState.SOLD
    await record_transition(
        s,
        lead_id=request.lead_id,
        from_state=None,
        to_state=current_state,
        event_type=event_type,
        task_name=task_name,
        status=request.status,
        idempotency_key=build_transition_idempotency_key(
            lead_id=request.lead_id,
            from_state=None,
            to_state=current_state,
            event_type=event_type,
            task_name=task_name,
            version=f"return:{request.id}:{action}",
        ),
        payload={
            "return_request_id": str(request.id),
            "post_result_id": str(result.id),
            "buyer_id": str(request.buyer_id),
            "reason": request.reason,
            "action": action,
            "operator": operator,
            "credited_cents": credited_cents,
            "policy_version": policy_version,
        },
    )
    await s.flush()
    return {
        "return_request_id": str(request.id),
        "lead_id": str(request.lead_id),
        "buyer_id": str(request.buyer_id),
        "status": request.status,
        "credited_cents": credited_cents,
        "auto_decided": operator == "autopilot-policy",
        "policy_version": policy_version,
        "wallet": _buyer_wallet_response(buyer),
    }


def _return_request_response(request: ReturnRequest) -> dict[str, Any]:
    return {
        "return_request_id": str(request.id),
        "post_result_id": str(request.post_result_id),
        "lead_id": str(request.lead_id),
        "buyer_id": str(request.buyer_id),
        "reason": request.reason,
        "status": request.status,
        "requested_by": request.requested_by,
        "reviewed_by": request.reviewed_by,
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else None,
    }


@app.get("/v1/admin/launch-readiness")
async def launch_readiness(
    market_state: str | None = Query(default=None, min_length=2, max_length=2),
    market_zip: str | None = Query(default=None, min_length=3, max_length=10),
    service: str | None = Query(default=None, min_length=1, max_length=64),
    campaign_budget_cents: int = Query(default=100_000, ge=0),
) -> dict[str, Any]:
    """Evaluate local technical-readiness gates for a scoped paid-pilot launch."""
    if market_state and market_zip:
        raise HTTPException(400, "choose either market_state or market_zip, not both")

    zip_coverage_filter = or_(
        func.jsonb_array_length(BuyerRow.target_zips) > 0,
        func.jsonb_array_length(BuyerRow.exclusive_zips) > 0,
    )
    buyer_scope = [BuyerRow.status == BuyerStatus.ACTIVE.value, BuyerRow.deposit_balance > 0]
    configured_scope = [
        BuyerRow.status == BuyerStatus.ACTIVE.value,
        BuyerRow.deposit_balance > 0,
        zip_coverage_filter,
        func.jsonb_array_length(BuyerRow.services) > 0,
        BuyerRow.daily_cap > 0,
        BuyerRow.monthly_budget > 0,
        BuyerRow.bid_per_lead_t1_t2 > 0,
        BuyerRow.bid_per_lead_t3 > 0,
    ]
    lead_scope = []
    activation_scope = []
    if market_state:
        lead_scope.append(LeadRow.state == market_state.upper())
    if market_zip:
        lead_scope.append(LeadRow.zip == market_zip)
        buyer_zip_filter = or_(
            BuyerRow.target_zips.contains([market_zip]),
            BuyerRow.exclusive_zips.contains([market_zip]),
        )
        buyer_scope.append(buyer_zip_filter)
        configured_scope.append(buyer_zip_filter)
        activation_scope.append(buyer_zip_filter)
    if service:
        normalized_service = service.strip().lower()
        lead_scope.append(LeadRow.requested_service == normalized_service)
        buyer_scope.append(BuyerRow.services.contains([normalized_service]))
        configured_scope.append(BuyerRow.services.contains([normalized_service]))
        activation_scope.append(BuyerRow.services.contains([normalized_service]))

    try:
        async with get_session() as s:
            funded_buyers = await s.scalar(
                select(func.count(BuyerRow.id)).where(and_(*buyer_scope))
            )
            configured_buyers = await s.scalar(
                select(func.count(BuyerRow.id)).where(and_(*configured_scope))
            )
            total_wallet_cents = await s.scalar(
                select(func.coalesce(func.sum(BuyerRow.deposit_balance * 100), 0)).where(
                    and_(*buyer_scope)
                )
            )
            runway_multiplier = Decimal(str(KPI_THRESHOLDS.pause_wallet_runway_days)) / Decimal(30)
            runway_ready_buyers = await s.scalar(
                select(func.count(BuyerRow.id)).where(
                    and_(*configured_scope),
                    BuyerRow.monthly_budget > 0,
                    BuyerRow.deposit_balance >= BuyerRow.monthly_budget * runway_multiplier,
                )
            )
            activation_query = select(BuyerRow)
            if activation_scope:
                activation_query = activation_query.where(and_(*activation_scope))
            scoped_buyers = (await s.execute(activation_query)).scalars().all()
            lead_ids_query = select(LeadRow.id)
            if lead_scope:
                lead_ids_query = lead_ids_query.where(and_(*lead_scope))
            lead_ids_subq = lead_ids_query.subquery()
            delivered = await s.scalar(
                select(func.count(PostResult.id)).where(
                    PostResult.delivered.is_(True),
                    PostResult.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            returned = await s.scalar(
                select(func.count(PostResult.id)).where(
                    PostResult.returned.is_(True),
                    PostResult.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            approved_return_requests = await s.scalar(
                select(func.count(ReturnRequest.id)).where(
                    ReturnRequest.status == "approved",
                    ReturnRequest.lead_id.in_(select(lead_ids_subq.c.id)),
                )
            )
            attributed_leads = await s.scalar(
                select(func.count(LeadRow.id)).where(
                    LeadRow.campaign_source.is_not(None),
                    LeadRow.campaign_source != "",
                    LeadRow.id.in_(select(lead_ids_subq.c.id)),
                )
            )
            matched_call_events = await s.scalar(
                select(func.count(CallEventRow.id)).where(
                    CallEventRow.lead_id.in_(select(lead_ids_subq.c.id))
                )
            )

        buyer_readiness = [_buyer_onboarding_readiness(buyer) for buyer in scoped_buyers]
        buyer_gap_counts: dict[str, int] = {}
        for readiness in buyer_readiness:
            for requirement in readiness["missing_requirements"]:
                buyer_gap_counts[requirement] = buyer_gap_counts.get(requirement, 0) + 1
        autopilot_ready_buyers = sum(
            1 for readiness in buyer_readiness if readiness["autopilot_ready"]
        )
        active_buyers_in_scope = sum(
            1 for buyer in scoped_buyers if buyer.status == BuyerStatus.ACTIVE.value
        )
        local_simulation_checks = {
            "synthetic_ping_post_routed_test_lead": int(delivered or 0) > 0,
            "synthetic_return_review_credit_flow_tested": int(returned or 0) > 0
            and int(approved_return_requests or 0) > 0,
            "synthetic_campaign_source_attribution_visible": int(attributed_leads or 0) > 0,
            "synthetic_call_tracking_ingested": int(matched_call_events or 0) > 0,
        }
        technical_checks = {
            "three_funded_buyers_in_scope": int(funded_buyers or 0) >= 3,
            "buyers_have_services_zips_caps_and_prices": int(configured_buyers or 0) >= 3,
            "buyers_are_activation_ready": autopilot_ready_buyers >= 3,
            "wallet_balance_covers_campaign_budget": int(total_wallet_cents or 0)
            >= campaign_budget_cents,
            "buyer_wallet_runway_covers_pause_threshold": int(runway_ready_buyers or 0) >= 3,
            "ping_post_routed_test_lead": int(delivered or 0) > 0,
            "return_review_credit_flow_tested": int(returned or 0) > 0
            and int(approved_return_requests or 0) > 0,
            "campaign_source_attribution_visible": int(attributed_leads or 0) > 0,
            "call_tracking_ingested": int(matched_call_events or 0) > 0,
        }
        buyer_delivery_approval = provider_live_approved(ProviderArea.BUYER_DELIVERY)
        payment_approval = provider_live_approved(ProviderArea.PAYMENTS)
        commercial_approval = buyer_delivery_approval and payment_approval
        checks = {
            **local_simulation_checks,
            **technical_checks,
            "buyer_delivery_live_approval_present": buyer_delivery_approval,
            "live_payment_approval_present": payment_approval,
            "commercial_launch_approval_present": commercial_approval,
        }
        local_simulation_ready = all(local_simulation_checks.values())
        technical_ready = all(technical_checks.values())
        ready = technical_ready and commercial_approval
        return {
            "scope": {
                "market_state": market_state.upper() if market_state else None,
                "market_zip": market_zip,
                "service": service.strip().lower() if service else None,
                "campaign_budget_cents": campaign_budget_cents,
            },
            "readiness_label": "commercial_paid_launch_ready"
            if ready
            else "technical_local_ready"
            if technical_ready
            else "local_simulation_ready"
            if local_simulation_ready
            else "not_ready",
            "local_simulation_ready": local_simulation_ready,
            "technical_local_ready": technical_ready,
            "commercial_paid_launch_ready": ready,
            "ready_for_paid_launch": ready,
            "checks": checks,
            "metrics": {
                "funded_buyers": int(funded_buyers or 0),
                "configured_buyers": int(configured_buyers or 0),
                "autopilot_ready_buyers": autopilot_ready_buyers,
                "runway_ready_buyers": int(runway_ready_buyers or 0),
                "required_runway_days": KPI_THRESHOLDS.pause_wallet_runway_days,
                "active_wallet_total_cents": int(total_wallet_cents or 0),
                "delivered_posts": int(delivered or 0),
                "returned_posts": int(returned or 0),
                "approved_return_requests": int(approved_return_requests or 0),
                "attributed_leads": int(attributed_leads or 0),
                "matched_call_events": int(matched_call_events or 0),
            },
            "buyer_activation_funnel": {
                "total_buyers_in_scope": len(scoped_buyers),
                "active_buyers": active_buyers_in_scope,
                "funded_buyers": int(funded_buyers or 0),
                "configured_buyers": int(configured_buyers or 0),
                "autopilot_ready_buyers": autopilot_ready_buyers,
                "wallet_runway_ready_buyers": int(runway_ready_buyers or 0),
                "activation_rate": _normalize_ratio(autopilot_ready_buyers, len(scoped_buyers)),
                "gap_counts": buyer_gap_counts,
            },
            "notes": [
                "ready_for_paid_launch remains false unless buyer delivery and live payment approvals are present",
                "market_state scopes lead evidence; market_zip scopes buyer target or exclusive zip coverage",
                "campaign_budget_cents defaults to a conservative $1,000 local validation threshold",
                "call tracking readiness uses local synthetic call webhook events matched to scoped leads",
                "buyer wallet runway must clear the configured pause threshold before technical readiness",
                "payment readiness can be proven locally with refill intents and synthetic refill events before Stripe approval",
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
                    or_(
                        func.jsonb_array_length(BuyerRow.target_zips) > 0,
                        func.jsonb_array_length(BuyerRow.exclusive_zips) > 0,
                    )
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
        "damage_type": lead.damage_type,
        "urgency": lead.urgency,
        "damage_tier": lead.damage_tier,
        "safety_flags": lead.safety_flags or [],
        "lead_class": lead.lead_class,
        "qualification_score": lead.qualification_score,
        "hold_for_review": lead.hold_for_review,
        "blocked_for_fraud": lead.blocked_for_fraud,
        "photo_count": len(lead.photo_s3_keys or []),
        "location_verification_status": lead.location_verification_status,
        "gps_accuracy_meters": lead.gps_accuracy_meters,
        "google_click_id_present": bool(lead.google_click_id),
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
    await check_exclusive_zip_conflict(exclude_buyer_id, exclusive_zips)


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
            "api_key_set": bool(buyer.api_key),
            "next_follow_up_at": buyer.next_follow_up_at.isoformat()
            if buyer.next_follow_up_at
            else None,
            "follow_up_date": buyer.follow_up_date.isoformat() if buyer.follow_up_date else None,
            "services": buyer.services or [],
            "services_offered": buyer.services_offered or [],
            "target_zips": buyer.target_zips or [],
            "exclusive_zips": buyer.exclusive_zips or [],
            "low_balance_threshold_cents": _decimal_to_cents(buyer.low_balance_threshold),
            "crm_low_balance_threshold_cents": buyer.low_balance_threshold_cents,
            "filter_expression": buyer.filter_expression,
            "webhook_url": buyer.webhook_url,
            "onboarding_readiness": _buyer_onboarding_readiness(buyer),
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
