"""Deterministic lead pipeline state machine.

The functions here are pure guardrails for orchestration code. They do not touch
the network or database; persistence belongs in workflow/audit layers.
"""

from __future__ import annotations

from enum import StrEnum


class PipelineState(StrEnum):
    CAPTURED = "captured"
    ENRICHED = "enriched"
    QUALIFIED = "qualified"
    AUCTIONED = "auctioned"
    SOLD = "sold"
    UNSOLD = "unsold"
    REJECTED = "rejected"
    NURTURED = "nurtured"
    NURTURE_FAILED = "nurture_failed"


class InvalidPipelineTransitionError(ValueError):
    """Raised when workflow code attempts an illegal lead state transition."""

    def __init__(self, from_state: PipelineState | str, to_state: PipelineState | str) -> None:
        super().__init__(f"invalid lead pipeline transition: {from_state!s} -> {to_state!s}")
        self.from_state = normalize_state(from_state)
        self.to_state = normalize_state(to_state)


_ALLOWED_TRANSITIONS: dict[PipelineState, frozenset[PipelineState]] = {
    PipelineState.CAPTURED: frozenset({PipelineState.ENRICHED}),
    PipelineState.ENRICHED: frozenset({PipelineState.QUALIFIED, PipelineState.REJECTED}),
    PipelineState.QUALIFIED: frozenset({PipelineState.AUCTIONED}),
    PipelineState.AUCTIONED: frozenset({PipelineState.SOLD, PipelineState.UNSOLD}),
    PipelineState.SOLD: frozenset(),
    PipelineState.UNSOLD: frozenset({PipelineState.NURTURED, PipelineState.NURTURE_FAILED}),
    PipelineState.REJECTED: frozenset({PipelineState.NURTURED, PipelineState.NURTURE_FAILED}),
    PipelineState.NURTURED: frozenset(),
    PipelineState.NURTURE_FAILED: frozenset(),
}


def normalize_state(state: PipelineState | str) -> PipelineState:
    return state if isinstance(state, PipelineState) else PipelineState(state)


def next_states(state: PipelineState | str) -> frozenset[PipelineState]:
    return _ALLOWED_TRANSITIONS[normalize_state(state)]


def can_transition(from_state: PipelineState | str, to_state: PipelineState | str) -> bool:
    return normalize_state(to_state) in next_states(from_state)


def assert_transition(from_state: PipelineState | str, to_state: PipelineState | str) -> None:
    if not can_transition(from_state, to_state):
        raise InvalidPipelineTransitionError(from_state, to_state)


def is_terminal(state: PipelineState | str) -> bool:
    return not next_states(state)
