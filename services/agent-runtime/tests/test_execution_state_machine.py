from uuid import uuid4

import pytest

from agent_runtime.execution import RunStateMachine, RunStatus


def test_valid_transitions_emit_expected_events() -> None:
    machine = RunStateMachine(run_id="run-1", lead_id=uuid4(), correlation_id=uuid4())

    started = machine.transition(RunStatus.RUNNING)
    assert started.event_type == "run.started"
    assert started.status == RunStatus.RUNNING

    awaiting = machine.transition(RunStatus.AWAITING_APPROVAL)
    assert awaiting.event_type == "run.awaiting_approval"

    resumed = machine.transition(RunStatus.RUNNING)
    assert resumed.event_type == "run.started"

    completed = machine.transition(RunStatus.COMPLETED)
    assert completed.event_type == "run.completed"


def test_invalid_transition_raises_value_error() -> None:
    machine = RunStateMachine(run_id="run-2", lead_id=None, correlation_id=None)
    machine.transition(RunStatus.RUNNING)
    machine.transition(RunStatus.COMPLETED)

    with pytest.raises(ValueError, match="invalid transition"):
        machine.transition(RunStatus.RUNNING)
