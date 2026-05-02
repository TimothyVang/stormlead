"""canonical pydantic models for stormlead.

these are the wire format. db rows mirror them. nats messages serialize them.
no service should redefine these.
"""

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


# ============================================================================
# core entities
# ============================================================================


class Storm(BaseModel):
    """normalized storm event. one per NHC atcf id or fema declaration id."""

    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    external_id: str  # nhc atcf id (AL092024) or fema disaster id (DR-4828-FL)
    name: str  # "hurricane helene", "milton", etc.
    source: str  # "nhc" | "nws" | "fema" | "spc"
    severity: StormSeverity
    affected_states: list[str] = Field(default_factory=list)  # ["FL", "GA", "SC"]
    affected_counties: list[str] = Field(default_factory=list)  # FIPS codes
    # postgis geom stored separately; this is a serializable bbox for messages
    bbox_wkt: str | None = None
    detected_at: datetime
    landfall_at: datetime | None = None
    declared_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)  # source payload for audit


class Lead(BaseModel):
    """a homeowner lead. PII-bearing. handle accordingly."""

    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    source: LeadSource
    status: LeadStatus = LeadStatus.NEW

    # pii (encrypted at rest in prod via pgcrypto + openbao keys)
    name: str
    phone_e164: str  # normalized to e164 at ingest
    email: str | None = None
    address_line1: str
    city: str
    state: str  # 2-letter
    zip: str
    lat: float | None = None
    lon: float | None = None

    # context
    storm_id: UUID | None = None
    damage_description: str | None = None
    damage_tier: DamageTier | None = None
    photo_s3_keys: list[str] = Field(default_factory=list)

    # tcpa-required audit trail
    consent_text: str  # exact disclosure shown
    consent_ip: str
    consent_user_agent: str
    consent_at: datetime
    page_url: str
    page_html_hash: str  # sha256 of page at submit time
    rrweb_session_s3_key: str | None = None
    trustedform_cert_url: str | None = None

    # enrichment
    property_avm: Decimal | None = None
    year_built: int | None = None
    owner_occupied: bool | None = None

    # scoring (set by qualify agent)
    qualification_score: float | None = None  # 0..1
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
    """a tree-service buyer in the roster."""

    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    company: str
    contact_email: str
    contact_phone_e164: str
    status: BuyerStatus = BuyerStatus.PENDING_VERIFICATION

    # licensing (we verify and store)
    license_number: str | None = None
    license_state: str | None = None
    license_verified_at: datetime | None = None

    # delivery
    webhook_url: str
    webhook_secret: str  # hmac key

    # pricing
    bid_per_lead_t1_t2: Decimal  # $45-100 typical
    bid_per_lead_t3: Decimal  # $150-250 typical
    bid_per_call: Decimal  # $80-120 typical

    # geographic + filter dsl (cel expression)
    filter_expression: str  # see filters.py
    daily_cap: int = 100
    monthly_budget: Decimal = Decimal(5000)

    # billing
    deposit_balance: Decimal = Decimal(0)
    lifetime_spend: Decimal = Decimal(0)

    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())
