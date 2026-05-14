"""auction unit tests. these exercise the pure logic, no db, no http.

for integration: see scripts/smoke_e2e.py.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from ping_post.api import _recommended_refill_cents
from ping_post.auction import (
    PingResponse,
    _apply_exclusive_zip_routing,
    _avm_band,
    _buyer_can_afford_bid,
    _buyer_delivery_allowed,
    _buyer_matches_paid_pilot_rules,
    _buyer_within_caps,
    _collect_bid_window_responses,
    _credit_failed_delivery,
    _debit_amount,
    _delivery_idempotency_key,
    _lead_can_enter_auction,
    _pick_winner,
    _ping_payload,
    _reserve_buyer_wallet,
    _should_retry_post,
    _sign_webhook,
)
from ping_post.buyer_activation import buyer_activation_readiness
from stormlead_core import (
    Buyer,
    BuyerSalesStage,
    BuyerStatus,
    DamageTier,
    Lead,
    LeadClass,
    LeadSource,
    LeadStatus,
)
from stormlead_core.filters import evaluate_filter


def _lead(
    state="FL",
    tier=DamageTier.TIER_3_ON_STRUCTURE,
    avm=400_000,
    lead_class=LeadClass.A,
    requested_service="tree_removal",
    safety_flags: list[str] | None = None,
) -> Lead:
    now = datetime.now(UTC)
    return Lead(
        id=uuid4(),
        source=LeadSource.LANDING_FORM,
        status=LeadStatus.QUALIFIED,
        name="Jane Doe",
        phone_e164="+15125550100",
        email="jane@stormlead.test",
        address_line1="100 Main St",
        city="Miami",
        state=state,
        zip="33101",
        damage_description="tree on garage",
        damage_type="roof_impact",
        urgency="same_day",
        damage_summary="Tree impact reported near a garage.",
        visible_risk_level="medium",
        estimated_job_size="large",
        buyer_notes="Verify structure involvement and safe equipment access.",
        damage_tier=tier,
        safety_flags=safety_flags or [],
        lead_class=lead_class,
        requested_service=requested_service,
        consent_text="I agree...",
        consent_ip="1.2.3.4",
        consent_user_agent="Mozilla/5.0",
        consent_at=now,
        page_url="https://stormlead.test/quote",
        page_html_hash="a" * 64,
        property_avm=Decimal(avm),
        qualification_score=0.92,
    )


def _buyer(filter_expr="lead.state == 'FL'") -> Buyer:
    return Buyer(
        name="Test",
        company="Test Co",
        contact_email="ops@test.co",
        contact_phone_e164="+15125550199",
        status=BuyerStatus.ACTIVE,
        webhook_url="https://buyer.stormlead.test/leads",
        webhook_secret="s3cret-test-only",  # noqa: S106 - inert test HMAC secret
        bid_per_lead_t1_t2=Decimal("65.00"),
        bid_per_lead_t3=Decimal("180.00"),
        bid_per_call=Decimal("100.00"),
        filter_expression=filter_expr,
        deposit_balance=Decimal("500.00"),
    )


def _activation_buyer(**overrides: object) -> SimpleNamespace:
    data: dict[str, object] = {
        "status": BuyerStatus.ACTIVE.value,
        "sales_stage": BuyerSalesStage.FUNDED.value,
        "notes": "terms accepted",
        "services": ["tree_removal"],
        "target_zips": ["33101"],
        "exclusive_zips": [],
        "deposit_balance": Decimal("500.00"),
        "low_balance_threshold": Decimal("100.00"),
        "daily_cap": 25,
        "monthly_budget": Decimal("5000.00"),
        "bid_per_lead_t1_t2": Decimal("65.00"),
        "bid_per_lead_t3": Decimal("180.00"),
        "bid_per_call": Decimal("100.00"),
        "webhook_url": "http://localhost:9999/webhook",
        "webhook_secret": "test-secret-32chars-minimum-ok",
        "api_key": "buyer-api-key",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class _FakeCapsSession:
    def __init__(self, scalar_results: list[int]) -> None:
        self._scalar_results = scalar_results

    async def __aenter__(self) -> _FakeCapsSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def scalar(self, *_args: object, **_kwargs: object) -> int:
        return self._scalar_results.pop(0)


class _FakeWalletSession:
    def __init__(self, *, rowcount: int = 1) -> None:
        self.rowcount = rowcount
        self.added: list[Any] = []

    async def __aenter__(self) -> _FakeWalletSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(rowcount=self.rowcount)

    def add(self, row: Any) -> None:
        self.added.append(row)


def test_avm_band_buckets() -> None:
    assert _avm_band(None) == "unknown"
    assert _avm_band(Decimal(100_000)) == "lt_150k"
    assert _avm_band(Decimal(250_000)) == "150k_300k"
    assert _avm_band(Decimal(2_000_000)) == "gt_1m"


def test_ping_payload_strips_pii() -> None:
    lead = _lead()
    p = _ping_payload(lead)
    assert "Jane Doe" not in str(p)
    assert "+15125550100" not in str(p)
    assert p["state"] == "FL"
    assert p["damage_tier"] == "tier_3_on_structure"
    assert p["damage_type"] == "roof_impact"
    assert p["urgency"] == "same_day"
    assert (
        p["damage_summary"]
        == "Roof impact reported; urgency same day; visible risk medium; estimated job large."
    )
    assert p["visible_risk_level"] == "medium"
    assert p["estimated_job_size"] == "large"
    assert (
        p["buyer_notes"]
        == "Pre-sale ping only; confirm access, crew size, and equipment after purchase."
    )
    # avm is banded, not exact
    assert "400000" not in str(p)


def test_ping_payload_uses_controlled_text_instead_of_structured_review_pii() -> None:
    lead = _lead()
    lead.damage_summary = "Homeowner John Doe needs removal near 100 Main St."
    lead.buyer_notes = "Email john@example.com or call 512-555-0100 before dispatch."

    payload = _ping_payload(lead)
    combined = f"{payload['damage_summary']} {payload['buyer_notes']}"

    assert "John" not in combined
    assert "Doe" not in combined
    assert "512-555-0100" not in combined
    assert "john@example.com" not in combined
    assert "100 Main" not in combined
    assert "Roof impact reported" in combined
    assert "Pre-sale ping only" in combined


def test_sign_webhook_is_deterministic() -> None:
    a = _sign_webhook("k", "1700000000", b'{"x":1}')
    b = _sign_webhook("k", "1700000000", b'{"x":1}')
    assert a == b
    assert a.startswith("v1,")


def test_delivery_idempotency_key_is_stable() -> None:
    lead_id = uuid4()
    buyer_id = uuid4()
    a = _delivery_idempotency_key(lead_id, buyer_id, 12000)
    b = _delivery_idempotency_key(lead_id, buyer_id, 12000)
    assert a == b
    assert len(a) == 64


def test_delivery_idempotency_key_changes_when_bid_changes() -> None:
    lead_id = uuid4()
    buyer_id = uuid4()
    assert _delivery_idempotency_key(lead_id, buyer_id, 9000) != _delivery_idempotency_key(
        lead_id, buyer_id, 9100
    )


def test_should_retry_post_for_5xx_and_429() -> None:
    assert _should_retry_post(500, None)
    assert _should_retry_post(503, None)
    assert _should_retry_post(429, None)
    assert not _should_retry_post(400, None)


def test_filter_matches_state() -> None:
    lead = _lead(state="FL")
    assert evaluate_filter("lead.state == 'FL'", lead).matches
    assert not evaluate_filter("lead.state == 'TX'", lead).matches


def test_filter_tier_and_avm() -> None:
    lead = _lead(tier=DamageTier.TIER_3_ON_STRUCTURE, avm=400_000)
    expr = "lead.damage_tier == 'tier_3_on_structure' && lead.property_avm > 250000.0"
    assert evaluate_filter(expr, lead).matches


def test_filter_broken_expression_does_not_match() -> None:
    lead = _lead()
    # invalid cel must NOT silently match
    assert not evaluate_filter("nonsense + ((", lead).matches


def test_pick_winner_takes_highest_bid() -> None:
    b1, b2 = uuid4(), uuid4()
    buyers = {
        b1: _buyer(),
        b2: _buyer(),
    }
    responses = [
        PingResponse(
            b1,
            accepted=True,
            bid_cents=18_000,
            response_ms=120,
            status_code=200,
            body=None,
            error=None,
        ),
        PingResponse(
            b2,
            accepted=True,
            bid_cents=22_000,
            response_ms=200,
            status_code=200,
            body=None,
            error=None,
        ),
    ]
    winner = _pick_winner(responses, buyers, DamageTier.TIER_3_ON_STRUCTURE)
    assert winner is not None
    pr, _winner_buyer = winner
    assert pr.buyer_id == b2
    assert pr.bid_cents == 22_000


def test_pick_winner_ties_break_by_speed() -> None:
    b1, b2 = uuid4(), uuid4()
    buyers = {b1: _buyer(), b2: _buyer()}
    responses = [
        PingResponse(
            b1,
            accepted=True,
            bid_cents=20_000,
            response_ms=300,
            status_code=200,
            body=None,
            error=None,
        ),
        PingResponse(
            b2,
            accepted=True,
            bid_cents=20_000,
            response_ms=120,
            status_code=200,
            body=None,
            error=None,
        ),
    ]
    winner = _pick_winner(responses, buyers, DamageTier.TIER_3_ON_STRUCTURE)
    assert winner is not None
    assert winner[0].buyer_id == b2  # faster wins the tie


def test_pick_winner_none_when_all_reject() -> None:
    b1 = uuid4()
    buyers = {b1: _buyer()}
    responses = [
        PingResponse(
            b1,
            accepted=False,
            bid_cents=None,
            response_ms=120,
            status_code=200,
            body=None,
            error=None,
        ),
    ]
    assert _pick_winner(responses, buyers, DamageTier.TIER_1_BRANCHES) is None


def test_pick_winner_skips_buyer_without_wallet_balance() -> None:
    b1, b2 = uuid4(), uuid4()
    broke = _buyer()
    broke.deposit_balance = Decimal("25.00")
    funded = _buyer()
    funded.deposit_balance = Decimal("500.00")
    buyers = {b1: broke, b2: funded}
    responses = [
        PingResponse(
            b1,
            accepted=True,
            bid_cents=20_000,
            response_ms=90,
            status_code=200,
            body=None,
            error=None,
        ),
        PingResponse(
            b2,
            accepted=True,
            bid_cents=18_000,
            response_ms=140,
            status_code=200,
            body=None,
            error=None,
        ),
    ]
    winner = _pick_winner(responses, buyers, DamageTier.TIER_3_ON_STRUCTURE)
    assert winner is not None
    assert winner[0].buyer_id == b2


def test_pick_winner_rejects_non_positive_bids() -> None:
    buyer_id = uuid4()
    buyers = {buyer_id: _buyer()}
    responses = [
        PingResponse(
            buyer_id,
            accepted=True,
            bid_cents=-1,
            response_ms=90,
            status_code=200,
            body=None,
            error=None,
        )
    ]

    assert _pick_winner(responses, buyers, DamageTier.TIER_3_ON_STRUCTURE) is None


def test_pick_winner_rejects_bid_below_configured_price() -> None:
    buyer = _buyer()
    buyers = {buyer.id: buyer}
    responses = [
        PingResponse(
            buyer.id,
            accepted=True,
            bid_cents=1,
            response_ms=90,
            status_code=200,
            body=None,
            error=None,
        )
    ]

    assert _pick_winner(responses, buyers, DamageTier.TIER_3_ON_STRUCTURE) is None


def test_wallet_helpers_convert_cents_to_dollars() -> None:
    buyer = _buyer()
    buyer.deposit_balance = Decimal("99.99")
    assert _buyer_can_afford_bid(buyer, 9999)
    assert not _buyer_can_afford_bid(buyer, 10000)
    assert not _buyer_can_afford_bid(buyer, 0)
    assert _debit_amount(12550) == Decimal("125.5")


async def test_reserve_buyer_wallet_records_reserved_debit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer_id = uuid4()
    lead_id = uuid4()
    fake_session = _FakeWalletSession(rowcount=1)
    monkeypatch.setattr("ping_post.auction.get_session", lambda: fake_session)

    assert await _reserve_buyer_wallet(buyer_id, lead_id, 18_000)

    assert len(fake_session.added) == 1
    event = fake_session.added[0]
    assert event.buyer_id == buyer_id
    assert event.lead_id == lead_id
    assert event.event_type == "lead.reserved"
    assert event.amount_cents == -18_000
    assert event.metadata_json == {"exclusive": True}


async def test_reserve_buyer_wallet_rejects_without_audit_event_when_balance_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeWalletSession(rowcount=0)
    monkeypatch.setattr("ping_post.auction.get_session", lambda: fake_session)

    assert not await _reserve_buyer_wallet(uuid4(), uuid4(), 18_000)
    assert fake_session.added == []


async def test_failed_delivery_credit_records_refund_audit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer_id = uuid4()
    lead_id = uuid4()
    fake_session = _FakeWalletSession(rowcount=1)
    monkeypatch.setattr("ping_post.auction.get_session", lambda: fake_session)

    await _credit_failed_delivery(buyer_id, lead_id, 18_000, 500)

    assert len(fake_session.added) == 1
    event = fake_session.added[0]
    assert event.buyer_id == buyer_id
    assert event.lead_id == lead_id
    assert event.event_type == "lead.delivery_failed_credit"
    assert event.amount_cents == 18_000
    assert event.metadata_json == {"post_result_status_code": 500}


def test_buyer_activation_readiness_requires_launch_fields() -> None:
    ready = buyer_activation_readiness(_activation_buyer())
    assert ready["autopilot_ready"] is True

    missing_api_key = buyer_activation_readiness(_activation_buyer(api_key=None))
    assert missing_api_key["autopilot_ready"] is False
    assert "api_key_ready" in missing_api_key["missing_requirements"]


def test_buyer_activation_readiness_counts_exclusive_zip_as_coverage() -> None:
    readiness = buyer_activation_readiness(
        _activation_buyer(target_zips=[], exclusive_zips=["33101"])
    )

    assert readiness["zip_ready"] is True
    assert readiness["coverage_zips"] == ["33101"]


def test_buyer_delivery_stays_local_before_commercial_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", raising=False)
    assert _buyer_delivery_allowed("http://localhost:9999/webhook")
    assert _buyer_delivery_allowed("http://host.docker.internal:9999/webhook")
    assert not _buyer_delivery_allowed("https://buyer.stormlead.test/leads")


def test_buyer_delivery_requires_approved_https_host_after_commercial_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.delenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", raising=False)

    assert not _buyer_delivery_allowed("https://buyer.stormlead.test/leads")

    monkeypatch.setenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", "buyer.stormlead.test")
    monkeypatch.setattr(
        "stormlead_core.env_gate.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    assert _buyer_delivery_allowed("https://buyer.stormlead.test/leads")
    assert not _buyer_delivery_allowed("http://buyer.stormlead.test/leads")

    monkeypatch.setenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", "10.0.0.5")
    assert not _buyer_delivery_allowed("https://10.0.0.5/leads")

    monkeypatch.setenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", "buyer.stormlead.test")
    monkeypatch.setattr(
        "stormlead_core.env_gate.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("10.0.0.5", 443))],
    )
    assert not _buyer_delivery_allowed("https://buyer.stormlead.test/leads")


def test_debit_amount_handles_zero_bid() -> None:
    assert _debit_amount(0) == Decimal("0")


def test_paid_pilot_rules_block_class_c_and_d() -> None:
    buyer = _buyer()
    assert not _buyer_matches_paid_pilot_rules(buyer, _lead(lead_class=LeadClass.C))
    assert not _buyer_matches_paid_pilot_rules(buyer, _lead(lead_class=LeadClass.D))


def test_paid_pilot_rules_require_target_zip_when_configured() -> None:
    buyer = _buyer()
    buyer.target_zips = ["78701"]
    assert not _buyer_matches_paid_pilot_rules(buyer, _lead())
    buyer.target_zips = ["33101"]
    assert _buyer_matches_paid_pilot_rules(buyer, _lead())


def test_paid_pilot_rules_treat_exclusive_zip_as_coverage() -> None:
    buyer = _buyer()
    buyer.target_zips = []
    buyer.exclusive_zips = ["33101"]
    assert _buyer_matches_paid_pilot_rules(buyer, _lead())

    buyer.exclusive_zips = ["78701"]
    assert not _buyer_matches_paid_pilot_rules(buyer, _lead())


def test_exclusive_zip_routing_only_returns_exclusive_buyers() -> None:
    exclusive = _buyer()
    exclusive.exclusive_zips = [" 33101 "]
    general = _buyer()
    general.target_zips = ["33101"]

    routed = _apply_exclusive_zip_routing(
        _lead(), [general, exclusive], active_exclusive_owner_exists=True
    )

    assert routed == [exclusive]


def test_exclusive_zip_routing_does_not_spill_when_owner_unready() -> None:
    general = _buyer()
    general.target_zips = ["33101"]

    routed = _apply_exclusive_zip_routing(_lead(), [general], active_exclusive_owner_exists=True)

    assert routed == []


def test_paid_pilot_rules_require_requested_service_when_configured() -> None:
    buyer = _buyer()
    buyer.services = ["roofing"]
    assert not _buyer_matches_paid_pilot_rules(buyer, _lead(requested_service="tree_removal"))
    buyer.services = ["tree_removal"]
    assert _buyer_matches_paid_pilot_rules(buyer, _lead(requested_service="tree_removal"))


@pytest.mark.parametrize(
    ("delivered_today", "gross_spend_month_cents", "expected"),
    [(1, 19_999, True), (2, 0, False), (0, 20_000, False)],
)
async def test_buyer_within_caps_enforces_daily_and_monthly_limits(
    delivered_today: int,
    gross_spend_month_cents: int,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer = _buyer()
    buyer.daily_cap = 2
    buyer.monthly_budget = Decimal("200.00")
    monkeypatch.setattr(
        "ping_post.auction.get_session",
        lambda: _FakeCapsSession([delivered_today, gross_spend_month_cents]),
    )

    assert await _buyer_within_caps(buyer) is expected


def test_lead_blocked_or_hold_is_not_auctioned() -> None:
    lead = _lead()
    lead.blocked_for_fraud = True
    assert _lead_can_enter_auction(lead) == (False, "blocked_for_fraud")

    lead.blocked_for_fraud = False
    lead.hold_for_review = True
    assert _lead_can_enter_auction(lead) == (False, "held_for_review")


def test_low_score_or_cd_class_goes_to_manual_review() -> None:
    lead = _lead()
    lead.score = 0.4
    ok, reason = _lead_can_enter_auction(lead)
    assert not ok
    assert reason == "score_below_hold_threshold"

    lead2 = _lead(lead_class=LeadClass.C)
    lead2.score = 0.7
    ok2, reason2 = _lead_can_enter_auction(lead2)
    assert not ok2
    assert reason2 == "class_requires_review"

    lead3 = _lead(lead_class=LeadClass.D)
    lead3.score = 0.99
    ok3, reason3 = _lead_can_enter_auction(lead3)
    assert not ok3
    assert reason3 == "class_requires_review"


def test_life_safety_lead_requires_review_before_auction() -> None:
    lead = _lead(tier=DamageTier.TIER_4_LIFE_SAFETY, safety_flags=["power_line"])

    ok, reason = _lead_can_enter_auction(lead)

    assert not ok
    assert reason == "safety_review_required"


def test_restricted_resale_source_is_not_auctioned() -> None:
    lead = _lead()
    lead.campaign_source = "google_lsa"

    ok, reason = _lead_can_enter_auction(lead)

    assert not ok
    assert reason == "restricted_source_no_resale"


def test_recommended_refill_is_zero_above_threshold() -> None:
    assert (
        _recommended_refill_cents(
            balance_cents=20_000,
            threshold_cents=15_000,
            monthly_budget_cents=100_000,
            delivered_today=2,
            gross_spend_today_cents=20_000,
        )
        == 0
    )


def test_recommended_refill_triggers_at_threshold() -> None:
    assert (
        _recommended_refill_cents(
            balance_cents=15_000,
            threshold_cents=15_000,
            monthly_budget_cents=100_000,
            delivered_today=0,
            gross_spend_today_cents=0,
        )
        == 25_000
    )


def test_recommended_refill_uses_largest_buffer_below_threshold() -> None:
    assert (
        _recommended_refill_cents(
            balance_cents=5_000,
            threshold_cents=15_000,
            monthly_budget_cents=100_000,
            delivered_today=2,
            gross_spend_today_cents=20_000,
        )
        == 30_000
    )


async def test_bid_window_preserves_completed_bids_and_times_out_only_pending() -> None:
    fast_a = _buyer()
    fast_b = _buyer()
    slow = _buyer()
    buyers = [fast_a, slow, fast_b]

    async def ping_buyer(buyer: Buyer) -> PingResponse:
        if buyer.id == slow.id:
            await asyncio.sleep(0.05)
        return PingResponse(
            buyer_id=buyer.id,
            accepted=buyer.id != slow.id,
            bid_cents=12_000 if buyer.id == fast_a.id else 10_000,
            response_ms=10,
            status_code=200,
            body=None,
            error=None,
        )

    responses = await _collect_bid_window_responses(
        lead_id=uuid4(), buyers=buyers, ping_buyer=ping_buyer, bid_window_s=0.01
    )

    by_buyer = {response.buyer_id: response for response in responses}
    assert by_buyer[fast_a.id].accepted
    assert by_buyer[fast_b.id].accepted
    assert not by_buyer[slow.id].accepted
    assert by_buyer[slow.id].error == "timeout"
