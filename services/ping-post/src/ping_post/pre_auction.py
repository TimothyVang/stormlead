from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re

from stormlead_core.models import Lead, LeadStatus, QualityScore


@dataclass(frozen=True)
class PreAuctionDecision:
    dedup_key: str
    quality: QualityScore
    proceed_to_auction: bool
    status: LeadStatus
    reason: str | None
    factors: dict[str, float | str]


def _normalize_phone(phone_e164: str) -> str:
    return re.sub(r"\D", "", phone_e164)


def _normalize_address(address_line1: str, city: str, state: str, zip_code: str) -> str:
    normalized = f"{address_line1}|{city}|{state}|{zip_code}".strip().lower()
    normalized = re.sub(r"[^a-z0-9| ]", "", normalized)
    return re.sub(r"\s+", " ", normalized)


def build_dedup_key(lead: Lead, *, window_minutes: int = 60) -> str:
    epoch_bucket = int(lead.created_at.replace(tzinfo=timezone.utc).timestamp() // (window_minutes * 60))
    payload = "|".join(
        [
            _normalize_phone(lead.phone_e164),
            _normalize_address(lead.address_line1, lead.city, lead.state, lead.zip),
            str(epoch_bucket),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_quality_score(lead: Lead) -> QualityScore:
    factors: dict[str, float] = {
        "has_damage_tier": 1.0 if lead.damage_tier else 0.0,
        "has_property_avm": 1.0 if lead.property_avm is not None else 0.0,
        "has_owner_occupied": 1.0 if lead.owner_occupied is not None else 0.0,
        "has_requested_service": 1.0 if bool(lead.requested_service) else 0.0,
        "has_contact_email": 1.0 if bool(lead.email) else 0.0,
    }
    score = round(sum(factors.values()) / len(factors), 4)
    return QualityScore(score=score, factors=factors)


def evaluate_pre_auction(
    lead: Lead,
    *,
    known_dedup_keys: set[str],
    now: datetime | None = None,
    min_quality_score: float = 0.6,
) -> PreAuctionDecision:
    dedup_key = build_dedup_key(lead)
    quality = compute_quality_score(lead)
    factors: dict[str, float | str] = dict(quality.factors)
    factors["min_quality_threshold"] = min_quality_score
    factors["evaluated_at"] = (now or datetime.now(timezone.utc)).isoformat()

    if dedup_key in known_dedup_keys:
        return PreAuctionDecision(
            dedup_key=dedup_key,
            quality=quality,
            proceed_to_auction=False,
            status=LeadStatus.REJECTED,
            reason="duplicate_submission",
            factors=factors,
        )

    if quality.score < min_quality_score:
        return PreAuctionDecision(
            dedup_key=dedup_key,
            quality=quality,
            proceed_to_auction=False,
            status=LeadStatus.QUALIFYING,
            reason="low_confidence_manual_review",
            factors=factors,
        )

    return PreAuctionDecision(
        dedup_key=dedup_key,
        quality=quality,
        proceed_to_auction=True,
        status=LeadStatus.QUALIFIED,
        reason=None,
        factors=factors,
    )
