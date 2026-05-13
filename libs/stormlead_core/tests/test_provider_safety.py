from __future__ import annotations

from stormlead_core.provider_safety import (
    ProviderArea,
    provider_decision,
    provider_kill_switch_change_plan,
    provider_pause_snapshot,
    provider_url_allowed,
)


def test_provider_safety_allows_local_targets(monkeypatch) -> None:
    monkeypatch.delenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", raising=False)

    decision = provider_decision(
        ProviderArea.BUYER_DELIVERY,
        action="buyer webhook delivery",
        target_url="http://localhost:9999/webhook",
    )

    assert decision.allowed
    assert not decision.external


def test_provider_safety_blocks_external_without_area_approval(monkeypatch) -> None:
    monkeypatch.delenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", raising=False)
    monkeypatch.delenv("STORMLEAD_APPROVE_BUYER_DELIVERY_LIVE", raising=False)
    monkeypatch.setenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", "buyer.example.com")

    assert not provider_url_allowed(
        ProviderArea.BUYER_DELIVERY,
        action="buyer webhook delivery",
        target_url="https://buyer.example.com/leads",
    )


def test_provider_safety_allows_approved_external_host(monkeypatch) -> None:
    monkeypatch.setenv("STORMLEAD_APPROVE_BUYER_DELIVERY_LIVE", "true")
    monkeypatch.setenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", "buyer.example.com")
    monkeypatch.setattr(
        "stormlead_core.env_gate.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )

    decision = provider_decision(
        ProviderArea.BUYER_DELIVERY,
        action="buyer webhook delivery",
        target_url="https://buyer.example.com/leads",
    )

    assert decision.allowed
    assert decision.external
    assert decision.live_mode


def test_provider_safety_pause_overrides_approval(monkeypatch) -> None:
    monkeypatch.setenv("STORMLEAD_APPROVE_BUYER_DELIVERY_LIVE", "true")
    monkeypatch.setenv("STORMLEAD_PAUSE_BUYER_DELIVERY", "true")

    decision = provider_decision(
        ProviderArea.BUYER_DELIVERY,
        action="buyer webhook delivery",
        target_url="http://localhost:9999/webhook",
    )

    assert not decision.allowed
    assert decision.reason == "buyer_delivery is paused"


def test_provider_safety_blocks_live_money_without_payment_approval(monkeypatch) -> None:
    monkeypatch.delenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", raising=False)
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)

    decision = provider_decision(
        ProviderArea.PAYMENTS,
        action="stripe live charge",
        live_money=True,
    )

    assert not decision.allowed
    assert decision.reason == "live provider action is not approved"


def test_global_commercial_approval_does_not_enable_sensitive_provider_areas(monkeypatch) -> None:
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)
    monkeypatch.delenv("STORMLEAD_APPROVE_ADS_LIVE", raising=False)
    monkeypatch.delenv("STORMLEAD_APPROVE_STORAGE_LIVE", raising=False)

    assert not provider_decision(
        ProviderArea.PAYMENTS,
        action="stripe live charge",
        live_money=True,
    ).allowed
    assert not provider_decision(
        ProviderArea.ADS,
        action="google ads campaign launch",
        live_spend=True,
    ).allowed
    assert not provider_decision(
        ProviderArea.STORAGE,
        action="production storage write",
        requires_live_approval=True,
    ).allowed


def test_provider_pause_snapshot_reports_kill_switch_envs(monkeypatch) -> None:
    monkeypatch.setenv("STORMLEAD_PAUSE_SMS", "true")
    monkeypatch.delenv("STORMLEAD_PAUSE_EMAIL", raising=False)

    snapshot = provider_pause_snapshot()

    assert snapshot["sms"]["paused"] is True
    assert snapshot["sms"]["pause_env"] == "STORMLEAD_PAUSE_SMS"
    assert snapshot["email"]["paused"] is False
    assert snapshot["email"]["pause_env"] == "STORMLEAD_PAUSE_EMAIL"


def test_provider_kill_switch_change_plan_is_approval_safe(monkeypatch) -> None:
    monkeypatch.delenv("STORMLEAD_PAUSE_SMS", raising=False)

    plan = provider_kill_switch_change_plan(
        ProviderArea.SMS,
        desired_paused=True,
        reason="delivery provider incident",
    )

    assert plan["area"] == "sms"
    assert plan["action"] == "pause"
    assert plan["current_paused"] is False
    assert plan["desired_paused"] is True
    assert plan["would_change"] is True
    assert plan["approval_required"] is True
    assert plan["required_config"] == {"STORMLEAD_PAUSE_SMS": "true"}
    assert plan["rollback_config"] == {"STORMLEAD_PAUSE_SMS": "false"}
    assert plan["would_contact_provider"] is False
    assert plan["would_mutate_runtime"] is False
