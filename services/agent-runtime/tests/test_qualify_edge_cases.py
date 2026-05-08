from __future__ import annotations

import json

import pytest
from agent_runtime.qualify import _class_from_score, _parse_qualification
from stormlead_core import DamageTier


def test_parse_qualification_valid_json() -> None:
    parsed = _parse_qualification(
        json.dumps(
            {
                "damage_tier": DamageTier.TIER_2_DOWN_GROUND.value,
                "qualification_score": 0.7,
                "reasoning": "Synthetic storm damage.",
                "rejection_reason": None,
            }
        )
    )
    assert parsed["qualification_score"] == 0.7
    assert parsed["damage_tier"] == DamageTier.TIER_2_DOWN_GROUND.value


def test_parse_qualification_score_above_one_raises() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        _parse_qualification(
            json.dumps(
                {
                    "damage_tier": DamageTier.TIER_1_BRANCHES.value,
                    "qualification_score": 1.5,
                }
            )
        )


def test_class_from_score_boundaries() -> None:
    assert _class_from_score(0.85) == "a"
    assert _class_from_score(0.849) == "b"
    assert _class_from_score(0.6) == "b"
    assert _class_from_score(0.599) == "c"
    assert _class_from_score(0.3) == "c"
    assert _class_from_score(0.299) == "d"
