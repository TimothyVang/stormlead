"""auction unit tests. these exercise the pure logic, no db, no http.

for integration: see scripts/smoke_e2e.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from ping_post.auction import (
    PingResponse,
    _avm_band,
    _buyer_can_afford_bid,
    _buyer_matches_paid_pilot_rules,
    _debit_amount,
    _pick_winner,
    _ping_payload,
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
