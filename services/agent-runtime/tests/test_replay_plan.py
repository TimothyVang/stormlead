from __future__ import annotations

from uuid import uuid4

from stormlead_core import PipelineState, build_replay_plan


def test_replay_plan_starts_uncaptured_lead_at_capture_event() -> None:
    lead_id = uuid4()
    plan = build_replay_plan(lead_id, None)
    assert plan.executable is True
    assert plan.event_name == "lead.captured"


def test_replay_plan_captured_branch_requeues_registered_qualifier() -> None:
    plan = build_replay_plan(uuid4(), PipelineState.CAPTURED)
    assert plan.executable is True
    assert plan.event_name == "lead.captured"


def test_replay_plan_qualified_branch_requeues_registered_auction() -> None:
    plan = build_replay_plan(uuid4(), PipelineState.QUALIFIED)
    assert plan.executable is True
    assert plan.event_name == "lead.qualified"


def test_replay_plan_unsold_branch_refuses_until_nurture_workflow_exists() -> None:
    plan = build_replay_plan(uuid4(), PipelineState.UNSOLD)
    assert plan.executable is True
    assert plan.event_name == "lead.unsold"


def test_replay_plan_sold_branch_refuses_by_default() -> None:
    plan = build_replay_plan(uuid4(), PipelineState.SOLD)
    assert plan.executable is False
    assert plan.event_name is None
    assert "terminal" in plan.reason
