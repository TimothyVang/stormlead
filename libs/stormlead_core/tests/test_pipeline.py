from __future__ import annotations

import pytest
from stormlead_core.pipeline import (
    InvalidPipelineTransitionError,
    PipelineState,
    assert_transition,
    can_transition,
    is_terminal,
    next_states,
)


def test_all_required_states_exist() -> None:
    assert {state.value for state in PipelineState} == {
        "captured",
        "enriched",
        "qualified",
        "auctioned",
        "sold",
        "unsold",
        "rejected",
        "nurtured",
        "nurture_failed",
    }


def test_allowed_transition_matrix() -> None:
    allowed = {
        PipelineState.CAPTURED: {PipelineState.ENRICHED},
        PipelineState.ENRICHED: {PipelineState.QUALIFIED, PipelineState.REJECTED},
        PipelineState.QUALIFIED: {PipelineState.AUCTIONED},
        PipelineState.AUCTIONED: {PipelineState.SOLD, PipelineState.UNSOLD},
        PipelineState.SOLD: set(),
        PipelineState.UNSOLD: {PipelineState.NURTURED, PipelineState.NURTURE_FAILED},
        PipelineState.REJECTED: {PipelineState.NURTURED, PipelineState.NURTURE_FAILED},
        PipelineState.NURTURED: set(),
        PipelineState.NURTURE_FAILED: set(),
    }
    for from_state in PipelineState:
        for to_state in PipelineState:
            assert can_transition(from_state, to_state) is (to_state in allowed[from_state])


def test_string_states_are_supported() -> None:
    assert can_transition("captured", "enriched") is True
    assert can_transition("captured", "sold") is False


def test_assert_transition_raises_clear_error_for_invalid_transition() -> None:
    with pytest.raises(InvalidPipelineTransitionError, match="captured -> sold"):
        assert_transition(PipelineState.CAPTURED, PipelineState.SOLD)


def test_terminal_states_have_no_next_states() -> None:
    assert next_states(PipelineState.SOLD) == frozenset()
    assert next_states(PipelineState.NURTURED) == frozenset()
    assert next_states(PipelineState.NURTURE_FAILED) == frozenset()
    assert is_terminal(PipelineState.SOLD) is True
    assert is_terminal(PipelineState.UNSOLD) is False
