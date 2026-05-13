from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from stormlead_core import BuyerSalesStage, BuyerStatus


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def _decimal_value(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def decimal_to_cents(value: Any) -> int:
    return int(_decimal_value(value) * Decimal(100))


def _positive_decimal(value: Any) -> bool:
    return _decimal_value(value) > 0


def _positive_int(value: Any) -> bool:
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    normalized = []
    seen = set()
    for raw in value:
        item = str(raw or "").strip().lower()
        if item and item not in seen:
            normalized.append(item)
            seen.add(item)
    return normalized


def buyer_exclusive_zips(buyer: Any) -> list[str]:
    return _string_list(getattr(buyer, "exclusive_zips", []))


def buyer_coverage_zips(buyer: Any) -> list[str]:
    zips = set(_string_list(getattr(buyer, "target_zips", [])))
    zips.update(buyer_exclusive_zips(buyer))
    return sorted(zips)


def buyer_activation_readiness(buyer: Any) -> dict[str, Any]:
    status = _enum_value(getattr(buyer, "status", None))
    sales_stage = _enum_value(getattr(buyer, "sales_stage", None))
    notes = str(getattr(buyer, "notes", "") or "").lower()
    services = _string_list(getattr(buyer, "services", []))
    coverage_zips = buyer_coverage_zips(buyer)
    balance_cents = decimal_to_cents(getattr(buyer, "deposit_balance", None))
    threshold_cents = decimal_to_cents(getattr(buyer, "low_balance_threshold", None))

    terms_accepted = sales_stage == BuyerSalesStage.FUNDED.value or "terms accepted" in notes
    service_ready = bool(services)
    zip_ready = bool(coverage_zips)
    wallet_ready = balance_cents > threshold_cents and balance_cents > 0
    caps_ready = _positive_int(getattr(buyer, "daily_cap", None)) and _positive_decimal(
        getattr(buyer, "monthly_budget", None)
    )
    pricing_ready = all(
        _positive_decimal(getattr(buyer, field, None))
        for field in ("bid_per_lead_t1_t2", "bid_per_lead_t3", "bid_per_call")
    )
    webhook_ready = bool(getattr(buyer, "webhook_url", None)) and bool(
        getattr(buyer, "webhook_secret", None)
    )
    api_key_ready = bool(getattr(buyer, "api_key", None))
    active_status_ready = status == BuyerStatus.ACTIVE.value

    requirements = {
        "active_status": active_status_ready,
        "terms_accepted": terms_accepted,
        "service_ready": service_ready,
        "zip_ready": zip_ready,
        "wallet_ready": wallet_ready,
        "caps_ready": caps_ready,
        "pricing_ready": pricing_ready,
        "webhook_ready": webhook_ready,
        "api_key_ready": api_key_ready,
    }
    autopilot_ready = all(requirements.values())
    missing_requirements = [name for name, ready in requirements.items() if not ready]

    return {
        **requirements,
        "budget_ready": caps_ready,
        "coverage_zips": coverage_zips,
        "balance_cents": balance_cents,
        "low_balance_threshold_cents": threshold_cents,
        "missing_requirements": missing_requirements,
        "auto_pause_recommended": active_status_ready and (not wallet_ready or not caps_ready),
        "auto_resume_ready": status == BuyerStatus.PAUSED.value and wallet_ready,
        "autopilot_ready": autopilot_ready,
    }
