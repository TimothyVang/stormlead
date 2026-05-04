from __future__ import annotations

from stormlead_db import LeadStateTransition


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
        "idempotency_key",
        "payload_json",
        "created_at",
    }.issubset(columns)


def test_idempotency_key_unique_constraint_declared() -> None:
    names = {constraint.name for constraint in LeadStateTransition.__table__.constraints}
    assert "uq_lead_state_transitions_idempotency_key" in names


def test_lead_created_at_order_index_declared() -> None:
    names = {index.name for index in LeadStateTransition.__table__.indexes}
    assert "ix_lead_state_transitions_lead_created_at" in names
    assert "ix_lead_state_transitions_to_state" in names
