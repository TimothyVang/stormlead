from __future__ import annotations

import re
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


def initial_quality_score(*, dwell_ms: int | None, has_email: bool, duplicate: bool) -> QualityScore:
    score = 1.0
    reasons: list[str] = []
    if duplicate:
        score -= 0.7
        reasons.append("duplicate_window_match")
    if dwell_ms is None or dwell_ms < 2000:
        score -= 0.25
        reasons.append("short_dwell")
    if not has_email:
        score -= 0.1
        reasons.append("missing_email")

    score = max(0.0, min(1.0, score))
    blocked = duplicate
    hold = score < 0.6 or duplicate
    return QualityScore(score=score, reason=",".join(reasons) or "baseline", hold=hold, blocked=blocked)
