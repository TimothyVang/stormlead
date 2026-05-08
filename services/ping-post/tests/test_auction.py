"""auction unit tests. these exercise the pure logic, no db, no http.

for integration: see scripts/smoke_e2e.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from ping_post.api import _recommended_refill_cents
from ping_post.auction import (
    PingResponse,
    _avm_band,
    _buyer_can_afford_bid,
    _buyer_matches_paid_pilot_rules,
    _debit_amount,
    _delivery_idempotency_key,
    _lead_can_enter_auction,
    _pick_winner,
    _ping_payload,
    _should_retry_post,
    _sign_webhook,
)
from stormlead_core import Buyer, BuyerStatus, DamageTier, Lead, LeadClass, LeadSource, LeadStatus
from stormlead_core.filters import evaluate_filter


def _lead(
    state="FL",
    tier=DamageTier.TIER_3_ON_STRUCTURE,
    avm=400_000,
    lead_class=LeadClass.A,
    requested_service="tree_removal",
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
        damage_tier=tier,
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
    # avm is banded, not exact
    assert "400000" not in str(p)


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
            bid_cents=8000,
            response_ms=120,
            status_code=200,
            body=None,
            error=None,
        ),
        PingResponse(
            b2,
            accepted=True,
            bid_cents=12000,
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
    assert pr.bid_cents == 12000


def test_pick_winner_ties_break_by_speed() -> None:
    b1, b2 = uuid4(), uuid4()
    buyers = {b1: _buyer(), b2: _buyer()}
    responses = [
        PingResponse(
            b1,
            accepted=True,
            bid_cents=10000,
            response_ms=300,
            status_code=200,
            body=None,
            error=None,
        ),
        PingResponse(
            b2,
            accepted=True,
            bid_cents=10000,
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
            bid_cents=15000,
            response_ms=90,
            status_code=200,
            body=None,
            error=None,
        ),
        PingResponse(
            b2,
            accepted=True,
            bid_cents=10000,
            response_ms=140,
            status_code=200,
            body=None,
            error=None,
        ),
    ]
    winner = _pick_winner(responses, buyers, DamageTier.TIER_3_ON_STRUCTURE)
    assert winner is not None
    assert winner[0].buyer_id == b2


def test_wallet_helpers_convert_cents_to_dollars() -> None:
    buyer = _buyer()
    buyer.deposit_balance = Decimal("99.99")
    assert _buyer_can_afford_bid(buyer, 9999)
    assert not _buyer_can_afford_bid(buyer, 10000)
    assert _debit_amount(12550) == Decimal("125.5")


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


def test_paid_pilot_rules_require_requested_service_when_configured() -> None:
    buyer = _buyer()
    buyer.services = ["roofing"]
    assert not _buyer_matches_paid_pilot_rules(buyer, _lead(requested_service="tree_removal"))
    buyer.services = ["tree_removal"]
    assert _buyer_matches_paid_pilot_rules(buyer, _lead(requested_service="tree_removal"))


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
