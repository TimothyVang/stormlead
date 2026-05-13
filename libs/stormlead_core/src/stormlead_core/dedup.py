from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_address(address_line1: str, city: str, state: str, zip_code: str) -> str:
    cleaned = " ".join(f"{address_line1} {city} {state} {zip_code}".upper().split())
    cleaned = re.sub(r"[^A-Z0-9 ]", "", cleaned)
    return cleaned


@dataclass(frozen=True)
class DuplicateWindow:
    phone_norm: str
    address_norm: str
    storm_id: UUID | None
    window_start: datetime
    window_end: datetime


@dataclass(frozen=True)
class QualityScore:
    score: float
    reason: str
    hold: bool
    blocked: bool


def build_duplicate_window(
    *,
    phone: str,
    address_line1: str,
    city: str,
    state: str,
    zip_code: str,
    storm_id: UUID | None,
    submitted_at: datetime,
    lookback_hours: int,
) -> DuplicateWindow:
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=UTC)
    return DuplicateWindow(
        phone_norm=normalize_phone(phone),
        address_norm=normalize_address(address_line1, city, state, zip_code),
        storm_id=storm_id,
        window_start=submitted_at - timedelta(hours=lookback_hours),
        window_end=submitted_at,
    )


HIGH_RISK_SAFETY_FLAGS = frozenset(
    {"power_line", "injury", "active_danger", "roof_impact", "structure_impact"}
)


def initial_quality_score(
    *,
    dwell_ms: int | None,
    has_email: bool,
    duplicate: bool,
    photo_count: int = 0,
    location_verified: bool = False,
    urgency: str | None = None,
    safety_flags: Sequence[str] | None = None,
) -> QualityScore:
    score = 1.0
    reasons: list[str] = []
    normalized_flags = {flag.strip().lower() for flag in safety_flags or [] if flag.strip()}
    if duplicate:
        score -= 0.7
        reasons.append("duplicate_window_match")
    if dwell_ms is None or dwell_ms < 2000:
        score -= 0.25
        reasons.append("short_dwell")
    if not has_email:
        score -= 0.1
        reasons.append("missing_email")
    if photo_count < 2:
        score -= 0.15
        reasons.append("insufficient_photos")
    if not location_verified:
        score -= 0.2
        reasons.append("location_not_verified")
    if urgency in {"emergency", "same_day"}:
        score = min(1.0, score + 0.05)
        reasons.append(f"urgency_{urgency}")
    high_risk_flags = normalized_flags & HIGH_RISK_SAFETY_FLAGS
    if high_risk_flags:
        reasons.append("safety_review_required:" + ",".join(sorted(high_risk_flags)))

    score = max(0.0, min(1.0, score))
    blocked = duplicate
    hold = score < 0.6 or duplicate or bool(high_risk_flags)
    return QualityScore(
        score=score, reason=",".join(reasons) or "baseline", hold=hold, blocked=blocked
    )
