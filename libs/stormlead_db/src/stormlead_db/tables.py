"""sqlalchemy table definitions.

design choices:
- one db, separate schemas per concern would be overkill at this size.
- timestamps utc only (postgres tz=utc enforced via image).
- foreign keys deferred where the lifecycle allows out-of-order writes.
- ping_attempts and call_events are timescale hypertables for time-series volume.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ============================================================================
# storms
# ============================================================================


class StormRow(Base):
    __tablename__ = "storms"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(16), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)

    affected_states: Mapped[list[str]] = mapped_column(JSONB, default=list)
    affected_counties: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # postgis geography for "what zips intersect this storm"
    geom = mapped_column(Geography("GEOMETRY", srid=4326), nullable=True)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    landfall_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


# ============================================================================
# buyers
# ============================================================================


class BuyerRow(Base):
    __tablename__ = "buyers"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(255))
    contact_email: Mapped[str] = mapped_column(String(255))
    contact_phone_e164: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(32), default="pending_verification", index=True)
    api_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)

    license_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    license_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    license_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    webhook_url: Mapped[str] = mapped_column(Text)
    webhook_secret: Mapped[str] = mapped_column(Text)  # encrypted via pgcrypto in prod

    bid_per_lead_t1_t2: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    bid_per_lead_t3: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    bid_per_call: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    filter_expression: Mapped[str] = mapped_column(Text)  # cel
    daily_cap: Mapped[int] = mapped_column(Integer, default=100)
    monthly_budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(5000))
    sales_stage: Mapped[str] = mapped_column(String(32), default="prospect", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    follow_up_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    services: Mapped[list[str]] = mapped_column(JSONB, default=list)
    services_offered: Mapped[list[str]] = mapped_column(JSONB, default=list)
    target_zips: Mapped[list[str]] = mapped_column(JSONB, default=list)
    exclusive_zips: Mapped[list[str]] = mapped_column(JSONB, default=list)
    low_balance_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    low_balance_threshold_cents: Mapped[int] = mapped_column(BigInteger, default=10000)

    deposit_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    lifetime_spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class CampaignRow(Base):
    """Paid-acquisition campaign registry; provider ingestion stays approval-gated."""

    __tablename__ = "campaigns"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    external_campaign_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    service: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    market_state: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    target_zips: Mapped[list[str]] = mapped_column(JSONB, default=list)
    daily_budget_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_campaign_id",
            name="uq_campaigns_platform_external_campaign_id",
        ),
        CheckConstraint(
            "platform IN ('local', 'google_ads', 'meta', 'microsoft_ads')",
            name="ck_campaigns_platform",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'archived')",
            name="ck_campaigns_status",
        ),
        CheckConstraint(
            "daily_budget_cents IS NULL OR daily_budget_cents >= 0",
            name="ck_campaigns_daily_budget_nonnegative",
        ),
    )


class CampaignSpendSnapshot(Base):
    """Daily spend snapshot keyed idempotently by platform campaign and date."""

    __tablename__ = "campaign_spend_snapshots"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("campaigns.id"))
    platform: Mapped[str] = mapped_column(String(32), index=True)
    external_campaign_id: Mapped[str] = mapped_column(String(128), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    spend_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(32), default="local", index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_campaign_id",
            "snapshot_date",
            name="uq_campaign_spend_platform_campaign_date",
        ),
        CheckConstraint("spend_cents >= 0", name="ck_campaign_spend_nonnegative"),
        CheckConstraint("clicks >= 0", name="ck_campaign_spend_clicks_nonnegative"),
        CheckConstraint(
            "impressions >= 0",
            name="ck_campaign_spend_impressions_nonnegative",
        ),
        CheckConstraint(
            "conversions >= 0",
            name="ck_campaign_spend_conversions_nonnegative",
        ),
        Index(
            "ix_campaign_spend_campaign_date",
            "campaign_id",
            text("snapshot_date DESC"),
        ),
    )


class TrackingLink(Base):
    """UTM/click-id mapping for paid lead attribution."""

    __tablename__ = "tracking_links"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("campaigns.id"))
    source: Mapped[str] = mapped_column(String(64), index=True)
    medium: Mapped[str] = mapped_column(String(64), index=True)
    campaign_slug: Mapped[str] = mapped_column(String(128), index=True)
    destination_url: Mapped[str] = mapped_column(Text)
    tracking_url: Mapped[str] = mapped_column(Text)
    utm_source: Mapped[str] = mapped_column(String(64), index=True)
    utm_medium: Mapped[str] = mapped_column(String(64), index=True)
    utm_campaign: Mapped[str] = mapped_column(String(128), index=True)
    click_id_param: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("tracking_url", name="uq_tracking_links_tracking_url"),
        CheckConstraint(
            "status IN ('active', 'paused', 'archived')",
            name="ck_tracking_links_status",
        ),
        Index("ix_tracking_links_campaign_status", "campaign_id", "status"),
    )


class BudgetActionLog(Base):
    """Deterministic budget pacing decision audit; provider mutations are separate."""

    __tablename__ = "budget_action_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("campaigns.id"))
    platform: Mapped[str] = mapped_column(String(32), index=True)
    external_campaign_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    decision_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('auto_pause', 'propose_increase', 'block_increase', 'hold')",
            name="ck_budget_action_logs_action",
        ),
        CheckConstraint(
            "status IN ('planned', 'approval_required', 'applied', 'blocked', 'skipped')",
            name="ck_budget_action_logs_status",
        ),
        Index(
            "uq_budget_action_logs_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_budget_action_logs_campaign_created", "campaign_id", text("created_at DESC")),
    )


# ============================================================================
# leads
# ============================================================================


class LeadRow(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="new")
    capture_webhook_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capture_event_emitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    capture_event_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    capture_event_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # pii (encrypt at rest in prod via pgcrypto + openbao key)
    name: Mapped[str] = mapped_column(String(255))
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(2), index=True)
    zip: Mapped[str] = mapped_column(String(10), index=True)
    normalized_address: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    geom = mapped_column(Geography("POINT", srid=4326), nullable=True)

    storm_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("storms.id"), nullable=True, index=True
    )
    damage_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    damage_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    urgency: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    damage_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    visible_risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    estimated_job_size: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    buyer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    damage_tier: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    photo_s3_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    safety_flags: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # tcpa audit (immutable after insert; enforce in code, not constraint)
    consent_text: Mapped[str] = mapped_column(Text)
    consent_version: Mapped[str] = mapped_column(String(64))
    consent_ip: Mapped[str] = mapped_column(String(45))
    consent_user_agent: Mapped[str] = mapped_column(Text)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    page_url: Mapped[str] = mapped_column(Text)
    page_html_hash: Mapped[str] = mapped_column(String(64))
    rrweb_session_s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    trustedform_cert_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    property_avm: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_occupied: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    qualification_score: Mapped[float | None] = mapped_column(nullable=True)
    lead_class: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    qualification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_service: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    campaign_source: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    google_click_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    first_touch_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_touch_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gps_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_accuracy_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    location_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    location_verification_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(nullable=True)
    score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hold_for_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    blocked_for_fraud: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_resale: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # for rag: embedding of damage description + photo summary
    embedding = mapped_column(Vector(1536), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        Index(
            "uq_lead_phone_address_storm_sellable",
            "phone_e164",
            "normalized_address",
            text("COALESCE(storm_id::text, '')"),
            unique=True,
            postgresql_where=text(
                "is_resale = false AND lead_class IN ('a', 'b') AND normalized_address IS NOT NULL"
            ),
        ),
        Index(
            "uq_leads_capture_webhook_id",
            "capture_webhook_id",
            unique=True,
            postgresql_where=text("capture_webhook_id IS NOT NULL"),
        ),
        CheckConstraint(
            "lead_class IS NULL OR lead_class IN ('a', 'b', 'c', 'd')", name="ck_leads_class"
        ),
        Index("ix_leads_state_zip_status", "state", "zip", "status"),
    )


class LeadStateTransition(Base):
    """Append-only workflow transition audit with retry idempotency."""

    __tablename__ = "lead_state_transitions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("leads.id"), index=True)
    from_state: Mapped[str] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    task_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="succeeded", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_lead_state_transitions_idempotency_key"),
        Index("ix_lead_state_transitions_lead_created_at", "lead_id", text("created_at DESC")),
        Index("ix_lead_state_transitions_to_state", "to_state"),
    )


# ============================================================================
# ping-post (the moat)
# ============================================================================


class PingAttempt(Base):
    """one row per (lead, buyer, attempt). hypertable on created_at."""

    __tablename__ = "ping_attempts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("leads.id"), index=True)
    buyer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buyers.id"), index=True
    )

    # ping payload (sanitized: no full pii)
    ping_payload: Mapped[dict] = mapped_column(JSONB)

    # response
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    bid_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )


class PostResult(Base):
    """the winning post for a lead. one per lead per attempt."""

    __tablename__ = "post_results"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("leads.id"), index=True)
    buyer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buyers.id"), index=True
    )
    delivery_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bid_cents: Mapped[int] = mapped_column(BigInteger)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned: Mapped[bool] = mapped_column(Boolean, default=False)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        Index(
            "uq_post_results_delivery_idempotency_key",
            "delivery_idempotency_key",
            unique=True,
            postgresql_where=text("delivery_idempotency_key IS NOT NULL"),
        ),
    )


class ReturnRequest(Base):
    """Buyer-submitted invalid-lead return request requiring review before credit."""

    __tablename__ = "return_requests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    post_result_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("post_results.id"), index=True
    )
    lead_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("leads.id"), index=True)
    buyer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buyers.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(64), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), default="buyer")
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'held', 'approved', 'rejected')",
            name="ck_return_requests_status",
        ),
        Index(
            "uq_return_requests_active_post_result",
            "post_result_id",
            unique=True,
            postgresql_where=text("status IN ('pending_review', 'held')"),
        ),
    )


class BillingEvent(Base):
    """append-only audit log. immutable. use for invoicing + disputes."""

    __tablename__ = "billing_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    buyer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buyers.id"), index=True
    )
    lead_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(
        String(64), index=True
    )  # lead.posted, lead.returned, deposit.added
    amount_cents: Mapped[int] = mapped_column(BigInteger)  # signed
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        Index(
            "uq_billing_events_external_event_id",
            "external_event_id",
            unique=True,
            postgresql_where=text("external_event_id IS NOT NULL"),
        ),
    )


class PaymentWebhookEvent(Base):
    """Provider payment webhook receipt audit before wallet credit decisions."""

    __tablename__ = "payment_webhook_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_event_id",
            name="uq_payment_webhook_events_provider_external_event_id",
        ),
        CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed')",
            name="ck_payment_webhook_events_status",
        ),
        Index("ix_payment_webhook_events_provider_created_at", "provider", text("created_at DESC")),
    )


class PaymentCustomer(Base):
    """Provider customer mapping for future buyer wallet top-ups."""

    __tablename__ = "payment_customers"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    buyer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buyers.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_customer_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        UniqueConstraint("buyer_id", "provider", name="uq_payment_customers_buyer_provider"),
        UniqueConstraint(
            "provider",
            "external_customer_id",
            name="uq_payment_customers_provider_external_customer_id",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'disabled')",
            name="ck_payment_customers_status",
        ),
    )


class WalletAutorefillRule(Base):
    """Disabled-by-default future auto-refill policy for buyer wallets."""

    __tablename__ = "wallet_autorefill_rules"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    buyer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buyers.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="stripe", index=True)
    status: Mapped[str] = mapped_column(String(32), default="disabled", index=True)
    threshold_cents: Mapped[int] = mapped_column(BigInteger)
    refill_amount_cents: Mapped[int] = mapped_column(BigInteger)
    daily_cap_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    monthly_cap_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        UniqueConstraint("buyer_id", "provider", name="uq_wallet_autorefill_rules_buyer_provider"),
        CheckConstraint(
            "status IN ('disabled', 'active', 'paused')",
            name="ck_wallet_autorefill_rules_status",
        ),
        CheckConstraint("threshold_cents >= 0", name="ck_wallet_autorefill_rules_threshold"),
        CheckConstraint("refill_amount_cents > 0", name="ck_wallet_autorefill_rules_refill_amount"),
        CheckConstraint("daily_cap_cents >= 0", name="ck_wallet_autorefill_rules_daily_cap"),
        CheckConstraint("monthly_cap_cents >= 0", name="ck_wallet_autorefill_rules_monthly_cap"),
    )


class OutreachAttempt(Base):
    """Provider-neutral outbound/inbound outreach audit row."""

    __tablename__ = "outreach_attempts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id"), nullable=True, index=True
    )
    buyer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buyers.id"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(16), default="outbound", index=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="recorded", index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('sms', 'email', 'voice')", name="ck_outreach_attempts_channel"
        ),
        CheckConstraint(
            "direction IN ('outbound', 'inbound')",
            name="ck_outreach_attempts_direction",
        ),
        CheckConstraint(
            "status IN ('recorded', 'queued', 'sent', 'delivered', 'received', 'failed', 'blocked')",
            name="ck_outreach_attempts_status",
        ),
        CheckConstraint(
            "status != 'queued' OR idempotency_key IS NOT NULL",
            name="ck_outreach_attempts_queued_has_idempotency",
        ),
        Index(
            "uq_outreach_attempts_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_outreach_attempts_provider_message",
            "provider",
            "external_message_id",
            unique=True,
            postgresql_where=text("provider IS NOT NULL AND external_message_id IS NOT NULL"),
        ),
        Index("ix_outreach_attempts_lead_created_at", "lead_id", text("created_at DESC")),
    )


class ChannelSuppression(Base):
    """Opt-out/suppression record shared by SMS, email, and voice."""

    __tablename__ = "channel_suppressions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    channel: Mapped[str] = mapped_column(String(16), index=True)
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    reason: Mapped[str] = mapped_column(String(64), default="opt_out", index=True)
    source_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('sms', 'email', 'voice')", name="ck_channel_suppressions_channel"
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_channel_suppressions_status",
        ),
        CheckConstraint(
            "phone_e164 IS NOT NULL OR email IS NOT NULL",
            name="ck_channel_suppressions_contact_present",
        ),
        CheckConstraint(
            "((channel IN ('sms', 'voice') AND phone_e164 IS NOT NULL) "
            "OR (channel = 'email' AND email IS NOT NULL))",
            name="ck_channel_suppressions_channel_contact_match",
        ),
        Index(
            "uq_channel_suppressions_active_phone",
            "channel",
            "phone_e164",
            unique=True,
            postgresql_where=text("status = 'active' AND phone_e164 IS NOT NULL"),
        ),
        Index(
            "uq_channel_suppressions_active_email",
            "channel",
            "email",
            unique=True,
            postgresql_where=text("status = 'active' AND email IS NOT NULL"),
        ),
        Index(
            "uq_channel_suppressions_provider_event",
            "channel",
            "source_provider",
            "external_event_id",
            unique=True,
            postgresql_where=text("source_provider IS NOT NULL AND external_event_id IS NOT NULL"),
        ),
    )


class ExceptionQueueItem(Base):
    """Durable operator exception item with owner/SLA state."""

    __tablename__ = "exception_queue"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    lead_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id"), nullable=True, index=True
    )
    buyer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("buyers.id"), nullable=True, index=True
    )
    return_request_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("return_requests.id"), nullable=True, index=True
    )
    post_result_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("post_results.id"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(128), index=True)
    recommended_action: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'warning', 'info')",
            name="ck_exception_queue_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'dismissed')",
            name="ck_exception_queue_status",
        ),
        Index(
            "uq_exception_queue_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_exception_queue_status_severity_sla", "status", "severity", "sla_due_at"),
    )


class CallEventRow(Base):
    """Call tracking webhook event matched to a lead when possible."""

    __tablename__ = "call_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    call_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    lead_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id"), nullable=True, index=True
    )
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    tracked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('answered', 'voicemail', 'no_answer', 'busy')",
            name="ck_call_events_outcome",
        ),
        Index("ix_call_events_lead_tracked_at", "lead_id", text("tracked_at DESC")),
    )


# ============================================================================
# self-evolution proposals
# ============================================================================


class SkillProposalRow(Base):
    """Pending Hermes skill/prompt proposal requiring operator review."""

    __tablename__ = "skill_proposals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    proposal_date: Mapped[date] = mapped_column(Date, index=True)
    proposal_type: Mapped[str] = mapped_column(String(32), index=True)
    skill_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    __table_args__ = (
        CheckConstraint(
            "proposal_type IN ('prompt_update', 'new_skill', 'retire_skill')",
            name="ck_skill_proposals_type",
        ),
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'applied')",
            name="ck_skill_proposals_status",
        ),
    )


class LearningProposal(Base):
    """Hermes learning proposal replay/canary state; live rollout stays gated."""

    __tablename__ = "learning_proposals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_proposal_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("skill_proposals.id"), nullable=True, index=True
    )
    proposal_date: Mapped[date] = mapped_column(Date, index=True)
    proposal_type: Mapped[str] = mapped_column(String(32), index=True)
    target_area: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_replay", index=True)
    canary_percent: Mapped[int] = mapped_column(Integer, default=0)
    guardrail_metric: Mapped[str] = mapped_column(String(64), default="conversion_rate")
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    rollback_threshold_pct: Mapped[float] = mapped_column(Float, default=5.0)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    proposal_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    replay_result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "proposal_type IN ('scoring_threshold', 'cadence_change', 'prompt_update')",
            name="ck_learning_proposals_type",
        ),
        CheckConstraint(
            "status IN ('pending_replay', 'replay_passed', 'canary_active', "
            "'rollback_triggered', 'pending_approval', 'promoted', 'rejected')",
            name="ck_learning_proposals_status",
        ),
        CheckConstraint(
            "canary_percent >= 0 AND canary_percent <= 100",
            name="ck_learning_proposals_canary_percent",
        ),
        Index(
            "uq_learning_proposals_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_learning_proposals_status_created", "status", text("created_at DESC")),
        Index("ix_learning_proposals_source_status", "source_proposal_id", "status"),
    )


# ============================================================================
# tcpa consent audit (form-receiver writes one per formbricks webhook delivery)
# ============================================================================


class ConsentAudit(Base):
    """tcpa-defensible audit row. one per formbricks webhook delivery.

    primary key is the standard-webhooks `webhook-id` header so retries
    are idempotent. raw_payload is the parsed envelope (jsonb) for
    forensic replay; the denormalized columns are for fast lookup +
    indexing without unwrapping json.
    """

    __tablename__ = "consent_audits"

    webhook_id: Mapped[str] = mapped_column(Text, primary_key=True)
    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    formbricks_response_id: Mapped[str] = mapped_column(Text)
    page_url: Mapped[str] = mapped_column(Text)
    ip: Mapped[str] = mapped_column(String(45))  # ipv4/v6
    user_agent: Mapped[str] = mapped_column(Text)
    consent_text: Mapped[str] = mapped_column(Text)
    consent_version: Mapped[str] = mapped_column(String(64))
    page_html_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dwell_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB)


class SuppressionEntry(Base):
    """Active opt-out/suppression entries checked before lead persistence."""

    __tablename__ = "suppression_entries"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(String(128), default="consumer_opt_out")
    source: Mapped[str] = mapped_column(String(64), default="privacy_request")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "phone_e164 IS NOT NULL OR email IS NOT NULL",
            name="ck_suppression_entries_contact",
        ),
        Index("ix_suppression_entries_phone", "phone_e164"),
        Index("ix_suppression_entries_email", "email"),
        Index(
            "uq_suppression_entries_phone_e164",
            "phone_e164",
            unique=True,
            postgresql_where=text("phone_e164 IS NOT NULL"),
        ),
        Index(
            "uq_suppression_entries_email",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )
