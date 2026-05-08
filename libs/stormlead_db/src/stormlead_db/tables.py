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


# ============================================================================
# leads
# ============================================================================


class LeadRow(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="new")

    # pii (encrypt at rest in prod via pgcrypto + openbao key)
    name: Mapped[str] = mapped_column(String(255))
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(2), index=True)
    zip: Mapped[str] = mapped_column(String(10), index=True)
    geom = mapped_column(Geography("POINT", srid=4326), nullable=True)

    storm_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("storms.id"), nullable=True, index=True
    )
    damage_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    damage_tier: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    photo_s3_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # tcpa audit (immutable after insert; enforce in code, not constraint)
    consent_text: Mapped[str] = mapped_column(Text)
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
    first_touch_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_touch_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(nullable=True)
    score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hold_for_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    blocked_for_fraud: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # for rag: embedding of damage description + photo summary
    embedding = mapped_column(Vector(1536), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        # idempotency: same phone + same hour = same lead
        UniqueConstraint("phone_e164", "page_html_hash", name="uq_lead_phone_hash"),
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
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
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
