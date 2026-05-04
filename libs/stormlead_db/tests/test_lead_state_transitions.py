from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Table
from stormlead_core import PipelineState
from stormlead_db import (
    LeadStateTransition,
    LeadTimelineEvent,
    build_transition_idempotency_key,
    summarize_transition_payload,
)


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


def test_summarize_transition_payload_redacts_pii_and_secrets() -> None:
    payload = {
        "qualification_score": 0.91,
        "email": "jane@example.test",
        "phone_e164": "+15125550100",
        "reasoning": "Strong storm damage signal for +15125550100 and jane@example.test.",
        "page_url": "https://stormlead.test/quote?email=jane@example.test&phone=15125550100",
        "nested": {
            "webhook_secret": "super-secret-value",
            "artifact_paths": ["testing/runs/demo/evidence.json"],
        },
    }

    summary = summarize_transition_payload(payload)

    assert summary["qualification_score"] == 0.91
    assert summary["email"] == "[redacted]"
    assert summary["phone_e164"] == "[redacted]"
    assert summary["page_url"] == "https://stormlead.test/quote"
    assert summary["nested"]["webhook_secret"] == "[redacted]"  # noqa: S105
    assert "jane@example.test" not in str(summary)
    assert "+15125550100" not in str(summary)
    assert "super-secret-value" not in str(summary)


def test_lead_timeline_event_serializes_for_admin_api() -> None:
    lead_id = uuid4()
    transition_id = uuid4()
    created_at = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    event = LeadTimelineEvent(
        id=transition_id,
        lead_id=lead_id,
        sequence=3,
        from_state="enriched",
        to_state="qualified",
        event_type="lead.qualified",
        task_name="agent_runtime.qualify_lead",
        workflow_run_id="run-123",
        status="succeeded",
        created_at=created_at,
        payload_summary={"qualification_score": 0.84},
    )

    assert event.as_dict() == {
        "id": str(transition_id),
        "lead_id": str(lead_id),
        "sequence": 3,
        "from_state": "enriched",
        "to_state": "qualified",
        "event_type": "lead.qualified",
        "task_name": "agent_runtime.qualify_lead",
        "workflow_run_id": "run-123",
        "status": "succeeded",
        "created_at": created_at.isoformat(),
        "payload_summary": {"qualification_score": 0.84},
    }
