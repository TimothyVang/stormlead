from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from agent_runtime.qualify import (
    _apply_qualification_result,
    _class_from_score,
    _local_simulation_result,
    _parse_qualification,
)
from stormlead_core import DamageTier, LeadClass, PipelineState
from stormlead_db import LeadRow


def _qualification_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "damage_tier": DamageTier.TIER_2_DOWN_GROUND.value,
        "qualification_score": 0.7,
        "damage_summary": "Downed tree blocking part of the yard.",
        "visible_risk_level": "low",
        "estimated_job_size": "medium",
        "buyer_notes": "Confirm tree size, access, and debris volume.",
        "safety_flags": [],
        "recommended_followup": "route",
        "reasoning": "Synthetic storm damage.",
        "rejection_reason": None,
    }
    payload.update(overrides)
    return payload


def test_parse_qualification_valid_json() -> None:
    parsed = _parse_qualification(json.dumps(_qualification_payload()))
    assert parsed["qualification_score"] == 0.7
    assert parsed["damage_tier"] == DamageTier.TIER_2_DOWN_GROUND.value
    assert parsed["damage_summary"] == "Downed tree blocking part of the yard."
    assert parsed["visible_risk_level"] == "low"
    assert parsed["estimated_job_size"] == "medium"
    assert parsed["buyer_notes"] == "Confirm tree size, access, and debris volume."
    assert parsed["safety_flags"] == []
    assert parsed["recommended_followup"] == "route"


def test_parse_qualification_rejects_unknown_followup() -> None:
    with pytest.raises(ValueError, match="recommended_followup"):
        _parse_qualification(
            json.dumps(
                _qualification_payload(
                    damage_tier=DamageTier.TIER_1_BRANCHES.value,
                    qualification_score=0.6,
                    recommended_followup="auto_sell",
                )
            )
        )


def test_parse_qualification_requires_followup_fields() -> None:
    missing_risk = _qualification_payload()
    missing_risk.pop("visible_risk_level")
    with pytest.raises(ValueError, match="visible_risk_level is required"):
        _parse_qualification(json.dumps(missing_risk))

    missing_followup = _qualification_payload()
    missing_followup.pop("recommended_followup")
    with pytest.raises(ValueError, match="recommended_followup is required"):
        _parse_qualification(json.dumps(missing_followup))


def test_parse_qualification_requires_structured_review_fields() -> None:
    missing_summary = _qualification_payload()
    missing_summary.pop("damage_summary")
    with pytest.raises(ValueError, match="damage_summary is required"):
        _parse_qualification(json.dumps(missing_summary))

    missing_job_size = _qualification_payload()
    missing_job_size.pop("estimated_job_size")
    with pytest.raises(ValueError, match="estimated_job_size is required"):
        _parse_qualification(json.dumps(missing_job_size))

    missing_buyer_notes = _qualification_payload()
    missing_buyer_notes.pop("buyer_notes")
    with pytest.raises(ValueError, match="buyer_notes is required"):
        _parse_qualification(json.dumps(missing_buyer_notes))

    missing_safety_flags = _qualification_payload()
    missing_safety_flags.pop("safety_flags")
    with pytest.raises(ValueError, match="safety_flags is required"):
        _parse_qualification(json.dumps(missing_safety_flags))

    unsupported_safety_flag = _qualification_payload(safety_flags=["homeowner_john_doe"])
    with pytest.raises(ValueError, match="unsupported"):
        _parse_qualification(json.dumps(unsupported_safety_flag))


def test_parse_qualification_redacts_common_pii_from_structured_review_text() -> None:
    parsed = _parse_qualification(
        json.dumps(
            _qualification_payload(
                damage_summary="Call John at (512) 555-0100 near 100 Main St.",
                buyer_notes="Email john@example.com or 512-555-0100 before dispatch.",
            )
        )
    )

    combined = f"{parsed['damage_summary']} {parsed['buyer_notes']}"
    assert "John" not in combined
    assert "512-555-0100" not in combined
    assert "(512) 555-0100" not in combined
    assert "john@example.com" not in combined
    assert "100 Main" not in combined
    assert "[redacted-phone]" in combined
    assert "[redacted-email]" in combined
    assert "[redacted-address]" in combined


def test_parse_qualification_uses_controlled_reasoning_and_rejection_reason() -> None:
    parsed = _parse_qualification(
        json.dumps(
            _qualification_payload(
                recommended_followup="reject",
                reasoning="Jane Doe at 100 Main St wants a call at 512-555-0100.",
                rejection_reason="Call John at john@example.com.",
            )
        )
    )

    assert parsed["reasoning"].startswith("Model classified")
    assert parsed["rejection_reason"] == "model_rejected"
    combined = f"{parsed['reasoning']} {parsed['rejection_reason']}"
    assert "Jane" not in combined
    assert "John" not in combined
    assert "100 Main" not in combined
    assert "512-555-0100" not in combined
    assert "john@example.com" not in combined


def test_parse_qualification_score_above_one_raises() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        _parse_qualification(json.dumps(_qualification_payload(qualification_score=1.5)))


def test_class_from_score_boundaries() -> None:
    assert _class_from_score(0.85) == "a"
    assert _class_from_score(0.849) == "b"
    assert _class_from_score(0.6) == "b"
    assert _class_from_score(0.599) == "c"
    assert _class_from_score(0.3) == "c"
    assert _class_from_score(0.299) == "d"


def test_resale_lead_stays_class_d_during_qualification() -> None:
    row = MagicMock(is_resale=True, safety_flags=[])
    parsed = _qualification_payload(
        damage_tier=DamageTier.TIER_3_ON_STRUCTURE.value,
        qualification_score=0.97,
        visible_risk_level="medium",
        reasoning="Strong damage signal.",
    )

    state = _apply_qualification_result(cast(LeadRow, row), parsed)

    assert state == PipelineState.REJECTED
    assert row.lead_class == LeadClass.D.value
    assert row.rejection_reason == "resale_duplicate"
    assert row.status == "rejected"


def test_life_safety_qualification_holds_for_human_review() -> None:
    row = MagicMock(is_resale=False, safety_flags=["power_line"])
    parsed = _qualification_payload(
        damage_tier=DamageTier.TIER_4_LIFE_SAFETY.value,
        qualification_score=0.91,
        visible_risk_level="high",
        recommended_followup="human_review",
        estimated_job_size="emergency",
        safety_flags=["power_line"],
        reasoning="Power line involvement requires review.",
    )

    state = _apply_qualification_result(cast(LeadRow, row), parsed)

    assert state == PipelineState.QUALIFIED
    assert row.hold_for_review is True
    assert row.status == "qualified"


def test_model_recommended_human_review_holds_without_safety_flag() -> None:
    row = MagicMock(is_resale=False, safety_flags=[])
    parsed = _qualification_payload(
        damage_tier=DamageTier.TIER_2_DOWN_GROUND.value,
        qualification_score=0.88,
        visible_risk_level="medium",
        recommended_followup="human_review",
        reasoning="Photos are ambiguous and need operator confirmation.",
    )

    state = _apply_qualification_result(cast(LeadRow, row), parsed)

    assert state == PipelineState.QUALIFIED
    assert row.hold_for_review is True
    assert row.status == "qualified"


def test_high_visible_risk_holds_without_other_review_signals() -> None:
    row = MagicMock(is_resale=False, safety_flags=[])
    parsed = _qualification_payload(
        damage_tier=DamageTier.TIER_2_DOWN_GROUND.value,
        qualification_score=0.86,
        visible_risk_level="high",
        recommended_followup="route",
        reasoning="Photo evidence shows elevated risk even without a structured flag.",
    )

    state = _apply_qualification_result(cast(LeadRow, row), parsed)

    assert state == PipelineState.QUALIFIED
    assert row.hold_for_review is True
    assert row.status == "qualified"


def test_model_recommended_reject_blocks_routing_without_reason() -> None:
    row = MagicMock(is_resale=False, safety_flags=[])
    parsed = _qualification_payload(
        damage_tier=DamageTier.TIER_1_BRANCHES.value,
        qualification_score=0.72,
        visible_risk_level="low",
        estimated_job_size="small",
        recommended_followup="reject",
        reasoning="The request does not match the paid tree-removal service.",
    )

    state = _apply_qualification_result(cast(LeadRow, row), parsed)

    assert state == PipelineState.REJECTED
    assert row.rejection_reason == "model_recommended_reject"
    assert row.status == "rejected"


def test_structured_review_fields_are_persisted_and_safety_flags_merge() -> None:
    row = MagicMock(is_resale=False, safety_flags=["power_line"])
    parsed = _qualification_payload(
        damage_summary="Tree limb reported near [redacted-address] after the storm.",
        visible_risk_level="medium",
        estimated_job_size="large",
        buyer_notes="Bring rigging crew; confirm access.",
        safety_flags=["roof_impact"],
    )

    _apply_qualification_result(cast(LeadRow, row), parsed)

    assert row.damage_summary == "Tree limb reported near [redacted-address] after the storm."
    assert row.visible_risk_level == "medium"
    assert row.estimated_job_size == "large"
    assert row.buyer_notes == "Bring rigging crew; confirm access."
    assert row.safety_flags == ["power_line", "roof_impact"]


def test_local_simulation_produces_structured_damage_review_without_ai_credentials() -> None:
    row = MagicMock(
        campaign_source="local_demo",
        campaign_id=None,
        first_touch_source=None,
        last_touch_source=None,
        blocked_for_fraud=False,
        score=0.91,
        safety_flags=[],
        damage_type="roof_impact",
    )

    result = _local_simulation_result(cast(LeadRow, row))

    assert result is not None
    assert result["damage_tier"] == DamageTier.TIER_3_ON_STRUCTURE.value
    assert result["damage_summary"] == "Tree impact on a structure or vehicle was reported."
    assert result["visible_risk_level"] == "medium"
    assert result["estimated_job_size"] == "large"
    assert (
        result["buyer_notes"]
        == "Verify structure involvement, access constraints, and equipment needs."
    )
    assert result["safety_flags"] == []
    assert result["recommended_followup"] == "route"


def test_local_simulation_filters_unsupported_safety_flags() -> None:
    row = MagicMock(
        campaign_source="local_demo",
        campaign_id=None,
        first_touch_source=None,
        last_touch_source=None,
        blocked_for_fraud=False,
        score=0.91,
        safety_flags=["roof_impact", "homeowner_john_doe"],
        damage_type="roof_impact",
    )

    result = _local_simulation_result(cast(LeadRow, row))

    assert result is not None
    assert result["safety_flags"] == ["roof_impact"]
