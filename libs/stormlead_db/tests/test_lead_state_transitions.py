from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Table
from stormlead_core import PipelineState
from stormlead_db import LeadStateTransition, build_transition_idempotency_key


def test_model_metadata_contains_lead_state_transitions_table() -> None:
    assert LeadStateTransition.__tablename__ == "lead_state_transitions"


def test_model_has_required_columns() -> None:
    columns = set(LeadStateTransition.__table__.columns.keys())
    assert {
        "id",
        "lead_id",
        "from_state",
        "to_state",
        "event_type",
        "task_name",
        "workflow_run_id",
        "status",
        "idempotency_key",
        "payload_json",
        "created_at",
    }.issubset(columns)


def test_idempotency_key_unique_constraint_declared() -> None:
    table = LeadStateTransition.__table__
    assert isinstance(table, Table)
    names = {constraint.name for constraint in table.constraints}
    assert "uq_lead_state_transitions_idempotency_key" in names


def test_lead_created_at_order_index_declared() -> None:
    table = LeadStateTransition.__table__
    assert isinstance(table, Table)
    names = {index.name for index in table.indexes}
    assert "ix_lead_state_transitions_lead_created_at" in names
    assert "ix_lead_state_transitions_to_state" in names


def test_transition_idempotency_key_is_deterministic() -> None:
    lead_id = uuid4()
    first = build_transition_idempotency_key(
        lead_id=lead_id,
        from_state=PipelineState.CAPTURED,
        to_state=PipelineState.ENRICHED,
        event_type="lead.enrich",
        task_name="lead.enrich",
    )
    second = build_transition_idempotency_key(
        lead_id=lead_id,
        from_state="captured",
        to_state="enriched",
        event_type="lead.enrich",
        task_name="lead.enrich",
    )
    assert first == second
    assert len(first) == 64
