from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ============================================================================
# enums
# ============================================================================


class StormSeverity(StrEnum):
    """nws/nhc-derived severity bucket."""

    WATCH = "watch"
    WARNING = "warning"
    LANDFALL = "landfall"
    POST_IMPACT = "post_impact"
    DECLARED = "declared"  # fema disaster declaration


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    REJECTED = "rejected"
    POSTING = "posting"
    SOLD = "sold"
    UNSOLD = "unsold"
    DIALING = "dialing"
    CONTACTED = "contacted"
    DEAD = "dead"


class LeadSource(StrEnum):
    LANDING_FORM = "landing_form"
    FACEBOOK_LEAD_AD = "facebook_lead_ad"
    GOOGLE_LSA = "google_lsa"
    INBOUND_CALL = "inbound_call"
    REFERRAL = "referral"


class LeadClass(StrEnum):
    A = "a"
    B = "b"
    C = "c"
    D = "d"


class DamageTier(StrEnum):
    """from photo classification + form description.

    pricing scales: tier-1 = $45-65, tier-2 = $75-100, tier-3 = $150-250
    """

    TIER_1_BRANCHES = "tier_1_branches"  # branches only, no structural risk
    TIER_2_DOWN_GROUND = "tier_2_down_ground"  # tree on ground, yard
    TIER_3_ON_STRUCTURE = "tier_3_on_structure"  # tree on house/garage/car
    TIER_4_LIFE_SAFETY = "tier_4_life_safety"  # tree on power line, blocking exit


class BuyerStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class BuyerSalesStage(StrEnum):
    PROSPECT = "prospect"
    CONTACTED = "contacted"
    AGREEMENT_SENT = "agreement_sent"
    FUNDED = "funded"
    CHURNED = "churned"


# ============================================================================
# workflow/agent safety models
# ============================================================================


class HumanOverrideMode(StrEnum):
    OFF = "off"
    LOW_CONFIDENCE_ONLY = "low_confidence_only"
    STRICT = "strict"


class WorkflowContext(BaseModel):
    correlation_id: UUID = Field(default_factory=uuid4)
    causation_id: UUID | None = None
    idempotency_key: str
    allow_charges_or_posts: bool = True
    human_override_mode: HumanOverrideMode = HumanOverrideMode.LOW_CONFIDENCE_ONLY
    min_confidence_for_autonomy: float = 0.7


class AgentDecisionOutput(BaseModel):
    decision: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
    idempotency_key: str
    requires_human_review: bool = False


class RetrySafeExecution(BaseModel):
    """shared helper for duplicate-prevention in repeated agent runs."""

    idempotency_key: str
    dedupe_scope: str
    should_execute_side_effects: bool


# ============================================================================
# agent role I/O contracts
# ============================================================================


class MarketSentinelInput(BaseModel):
    workflow: WorkflowContext
    storm_id: UUID | None = None
    affected_states: list[str] = Field(default_factory=list)
    open_lead_count: int = 0
    active_buyer_count: int = 0


class MarketSentinelOutput(AgentDecisionOutput):
    decision: str  # ready | monitor | hold
    readiness_score: float = Field(ge=0.0, le=1.0)


class LeadQualifierInput(BaseModel):
    workflow: WorkflowContext
    lead_id: UUID
    damage_description: str | None = None
    consent_present: bool = False
    photo_count: int = 0


class LeadQualifierOutput(AgentDecisionOutput):
    decision: str  # qualify | reject | review
    lead_class: LeadClass
    reason: str


class BuyerMatcherInput(BaseModel):
    workflow: WorkflowContext
    lead_id: UUID
    lead_class: LeadClass
    damage_tier: DamageTier | None = None
    candidate_buyer_ids: list[UUID] = Field(default_factory=list)


class RankedBuyer(BaseModel):
    buyer_id: UUID
    rank: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)


class BuyerMatcherOutput(AgentDecisionOutput):
    decision: str  # match | no_match | review
    eligible_buyers: list[RankedBuyer] = Field(default_factory=list)


class DisputeTriagerInput(BaseModel):
    workflow: WorkflowContext
    lead_id: UUID
    buyer_id: UUID | None = None
    dispute_reason: str
    requested_refund_cents: int | None = None


class DisputeTriagerOutput(AgentDecisionOutput):
    decision: str  # refund | deny | partial_refund | review
    recommended_refund_cents: int | None = None


class NurtureControllerInput(BaseModel):
    workflow: WorkflowContext
    lead_id: UUID
    hours_since_capture: int = 0
    prior_attempt_count: int = 0


class NurtureControllerOutput(AgentDecisionOutput):
    decision: str  # retry_contact | recycle | archive | review
    next_action_at: datetime | None = None


# ============================================================================
# core entities
# ============================================================================


class Storm(BaseModel):
    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)
    id: UUID = Field(default_factory=uuid4)
    external_id: str
    name: str
    source: str
    severity: StormSeverity
    affected_states: list[str] = Field(default_factory=list)
    affected_counties: list[str] = Field(default_factory=list)
    bbox_wkt: str | None = None
    detected_at: datetime
    landfall_at: datetime | None = None
    declared_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Lead(BaseModel):
    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)
    id: UUID = Field(default_factory=uuid4)
    source: LeadSource
    status: LeadStatus = LeadStatus.NEW
    name: str
    phone_e164: str
    email: str | None = None
    address_line1: str
    city: str
    state: str
    zip: str
    lat: float | None = None
    lon: float | None = None
    storm_id: UUID | None = None
    damage_description: str | None = None
    damage_tier: DamageTier | None = None
    photo_s3_keys: list[str] = Field(default_factory=list)
    consent_text: str
    consent_ip: str
    consent_user_agent: str
    consent_at: datetime
    page_url: str
    page_html_hash: str
    rrweb_session_s3_key: str | None = None
    trustedform_cert_url: str | None = None
    property_avm: Decimal | None = None
    year_built: int | None = None
    owner_occupied: bool | None = None
    qualification_score: float | None = None
    lead_class: LeadClass | None = None
    qualification_reason: str | None = None
    requested_service: str | None = None
    campaign_id: str | None = None
    campaign_source: str | None = None
    first_touch_source: str | None = None
    last_touch_source: str | None = None
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    @field_validator("phone_e164")
    @classmethod
    def must_be_e164(cls, v: str) -> str:
        if not v.startswith("+"):
            raise ValueError("phone must be e164 (start with +)")
        return v

    @field_validator("state")
    @classmethod
    def state_uppercase(cls, v: str) -> str:
        if len(v) != 2:
            raise ValueError("state must be 2-letter")
        return v.upper()


class Buyer(BaseModel):
    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company: str
    contact_email: str
    contact_phone_e164: str
    status: BuyerStatus = BuyerStatus.PENDING_VERIFICATION
    license_number: str | None = None
    license_state: str | None = None
    license_verified_at: datetime | None = None
    webhook_url: str
    webhook_secret: str
    bid_per_lead_t1_t2: Decimal
    bid_per_lead_t3: Decimal
    bid_per_call: Decimal
    filter_expression: str
    daily_cap: int = 100
    monthly_budget: Decimal = Decimal(5000)
    sales_stage: BuyerSalesStage = BuyerSalesStage.PROSPECT
    notes: str | None = None
    next_follow_up_at: datetime | None = None
    services: list[str] = Field(default_factory=list)
    target_zips: list[str] = Field(default_factory=list)
    exclusive_zips: list[str] = Field(default_factory=list)
    low_balance_threshold: Decimal = Decimal(0)
    deposit_balance: Decimal = Decimal(0)
    lifetime_spend: Decimal = Decimal(0)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())
