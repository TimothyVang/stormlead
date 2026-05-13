from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from stormlead_core.env_gate import is_approved_external_webhook_url, is_local_webhook_url


class ProviderArea(StrEnum):
    BUYER_DELIVERY = "buyer_delivery"
    NURTURE_WEBHOOK = "nurture_webhook"
    SMS = "sms"
    EMAIL = "email"
    VOICE = "voice"
    PAYMENTS = "payments"
    ADS = "ads"
    STORAGE = "storage"
    PAGE_ENRICHMENT = "page_enrichment"


@dataclass(frozen=True)
class ProviderDecision:
    area: ProviderArea
    allowed: bool
    reason: str
    action: str
    external: bool = False
    live_mode: bool = False
    target_url: str | None = None


_HOST_ENV_BY_AREA = {
    ProviderArea.BUYER_DELIVERY: "STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS",
    ProviderArea.NURTURE_WEBHOOK: "STORMLEAD_APPROVED_NURTURE_WEBHOOK_HOSTS",
    ProviderArea.SMS: "STORMLEAD_APPROVED_SMS_WEBHOOK_HOSTS",
    ProviderArea.EMAIL: "STORMLEAD_APPROVED_EMAIL_WEBHOOK_HOSTS",
    ProviderArea.VOICE: "STORMLEAD_APPROVED_VOICE_WEBHOOK_HOSTS",
    ProviderArea.PAYMENTS: "STORMLEAD_APPROVED_PAYMENT_WEBHOOK_HOSTS",
    ProviderArea.ADS: "STORMLEAD_APPROVED_ADS_WEBHOOK_HOSTS",
    ProviderArea.STORAGE: "STORMLEAD_APPROVED_STORAGE_HOSTS",
    ProviderArea.PAGE_ENRICHMENT: "STORMLEAD_APPROVED_PAGE_ENRICHMENT_HOSTS",
}

_APPROVAL_ENV_BY_AREA = {
    ProviderArea.BUYER_DELIVERY: "STORMLEAD_APPROVE_BUYER_DELIVERY_LIVE",
    ProviderArea.NURTURE_WEBHOOK: "STORMLEAD_APPROVE_NURTURE_WEBHOOK_LIVE",
    ProviderArea.SMS: "STORMLEAD_APPROVE_SMS_LIVE",
    ProviderArea.EMAIL: "STORMLEAD_APPROVE_EMAIL_LIVE",
    ProviderArea.VOICE: "STORMLEAD_APPROVE_VOICE_LIVE",
    ProviderArea.PAYMENTS: "STORMLEAD_APPROVE_PAYMENTS_LIVE",
    ProviderArea.ADS: "STORMLEAD_APPROVE_ADS_LIVE",
    ProviderArea.STORAGE: "STORMLEAD_APPROVE_STORAGE_LIVE",
    ProviderArea.PAGE_ENRICHMENT: "STORMLEAD_APPROVE_PAGE_ENRICHMENT_LIVE",
}

_PAUSE_ENV_BY_AREA = {
    ProviderArea.BUYER_DELIVERY: "STORMLEAD_PAUSE_BUYER_DELIVERY",
    ProviderArea.NURTURE_WEBHOOK: "STORMLEAD_PAUSE_NURTURE_WEBHOOK",
    ProviderArea.SMS: "STORMLEAD_PAUSE_SMS",
    ProviderArea.EMAIL: "STORMLEAD_PAUSE_EMAIL",
    ProviderArea.VOICE: "STORMLEAD_PAUSE_VOICE",
    ProviderArea.PAYMENTS: "STORMLEAD_PAUSE_PAYMENTS",
    ProviderArea.ADS: "STORMLEAD_PAUSE_ADS",
    ProviderArea.STORAGE: "STORMLEAD_PAUSE_STORAGE",
    ProviderArea.PAGE_ENRICHMENT: "STORMLEAD_PAUSE_PAGE_ENRICHMENT",
}

_GLOBAL_COMMERCIAL_APPROVAL_AREAS = {
    ProviderArea.BUYER_DELIVERY,
    ProviderArea.NURTURE_WEBHOOK,
}


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> set[str]:
    return {value.strip().lower() for value in os.getenv(name, "").split(",") if value.strip()}


def provider_live_approved(area: ProviderArea) -> bool:
    area_flag = _APPROVAL_ENV_BY_AREA[area]
    return _truthy_env(area_flag) or (
        area in _GLOBAL_COMMERCIAL_APPROVAL_AREAS
        and _truthy_env("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED")
    )


def provider_paused(area: ProviderArea) -> bool:
    return _truthy_env(_PAUSE_ENV_BY_AREA[area])


def provider_pause_snapshot() -> dict[str, dict[str, bool | str]]:
    return {
        area.value: {
            "paused": provider_paused(area),
            "approved": provider_live_approved(area),
            "pause_env": _PAUSE_ENV_BY_AREA[area],
            "approval_env": _APPROVAL_ENV_BY_AREA[area],
        }
        for area in ProviderArea
    }


def provider_kill_switch_change_plan(
    area: ProviderArea, *, desired_paused: bool, reason: str
) -> dict[str, object]:
    pause_env = _PAUSE_ENV_BY_AREA[area]
    current_paused = provider_paused(area)
    action = "pause" if desired_paused else "resume"
    desired_value = "true" if desired_paused else "false"
    rollback_value = "true" if current_paused else "false"

    return {
        "schema_version": 1,
        "area": area.value,
        "action": action,
        "reason": reason,
        "current_paused": current_paused,
        "desired_paused": desired_paused,
        "would_change": current_paused != desired_paused,
        "approval_required": True,
        "approval_reason": "provider kill-switch changes must be applied through approved config management",
        "pause_env": pause_env,
        "required_config": {pause_env: desired_value},
        "rollback_config": {pause_env: rollback_value},
        "operator_steps": [
            f"Get approval to {action} {area.value} provider actions.",
            f"Set {pause_env}={desired_value} in the approved runtime configuration.",
            "Redeploy or reload only the affected local/production service through the approved release path.",
            f"Verify /v1/admin/provider-kill-switches reports {area.value}.paused={str(desired_paused).lower()}.",
        ],
        "rollback_steps": [
            f"Set {pause_env}={rollback_value} to restore the pre-change pause state.",
            "Redeploy or reload through the approved release path and recheck the provider kill-switch snapshot.",
        ],
        "would_contact_provider": False,
        "would_mutate_runtime": False,
        "safe_to_call_without_provider_credentials": True,
    }


def provider_decision(
    area: ProviderArea,
    *,
    action: str,
    target_url: str | None = None,
    requires_live_approval: bool = False,
    live_money: bool = False,
    live_spend: bool = False,
) -> ProviderDecision:
    if provider_paused(area):
        return ProviderDecision(
            area, False, f"{area.value} is paused", action, target_url=target_url
        )

    if target_url:
        if is_local_webhook_url(target_url):
            return ProviderDecision(
                area, True, "local target allowed", action, target_url=target_url
            )
        hosts = _csv_env(_HOST_ENV_BY_AREA[area])
        if provider_live_approved(area) and is_approved_external_webhook_url(target_url, hosts):
            return ProviderDecision(
                area,
                True,
                "approved external target allowed",
                action,
                external=True,
                live_mode=True,
                target_url=target_url,
            )
        return ProviderDecision(
            area,
            False,
            "external target is not locally safe or approved",
            action,
            external=True,
            target_url=target_url,
        )

    if requires_live_approval or live_money or live_spend:
        if provider_live_approved(area):
            return ProviderDecision(
                area, True, "live provider action approved", action, live_mode=True
            )
        return ProviderDecision(area, False, "live provider action is not approved", action)

    return ProviderDecision(area, True, "local or dry-run action allowed", action)


def provider_url_allowed(area: ProviderArea, *, action: str, target_url: str) -> bool:
    return provider_decision(area, action=action, target_url=target_url).allowed
