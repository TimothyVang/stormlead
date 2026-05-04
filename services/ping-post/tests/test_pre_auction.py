from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from ping_post.pre_auction import build_dedup_key, evaluate_pre_auction
from stormlead_core import DamageTier, Lead, LeadSource, LeadStatus


def _lead(*, email: str | None = "jane@stormlead.test") -> Lead:
    now = datetime(2026, 5, 4, 12, 5, tzinfo=timezone.utc)
    return Lead(
        id=uuid4(),
        source=LeadSource.LANDING_FORM,
        status=LeadStatus.NEW,
        name="Jane Doe",
        phone_e164="+1 (512) 555-0100",
        email=email,
        address_line1="100 Main St.",
        city="Miami",
        state="FL",
        zip="33101",
        damage_description="tree on garage",
        damage_tier=DamageTier.TIER_3_ON_STRUCTURE,
        consent_text="I agree",
        consent_ip="1.2.3.4",
        consent_user_agent="Mozilla",
        consent_at=now,
        page_url="https://stormlead.test/quote",
        page_html_hash="a" * 64,
        property_avm=Decimal("400000"),
        owner_occupied=True,
        requested_service="tree_removal",
        created_at=now,
        updated_at=now,
    )


def test_duplicate_submission_is_blocked() -> None:
    lead = _lead()
    dedup_key = build_dedup_key(lead)
    decision = evaluate_pre_auction(lead, known_dedup_keys={dedup_key})
    assert not decision.proceed_to_auction
    assert decision.reason == "duplicate_submission"
    assert decision.status == LeadStatus.REJECTED


def test_low_quality_lead_goes_to_manual_review() -> None:
    lead = _lead(email=None)
    lead.damage_tier = None
    lead.property_avm = None
    decision = evaluate_pre_auction(lead, known_dedup_keys=set(), min_quality_score=0.7)
    assert not decision.proceed_to_auction
    assert decision.reason == "low_confidence_manual_review"
    assert decision.status == LeadStatus.QUALIFYING
