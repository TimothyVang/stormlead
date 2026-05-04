"""add lead state transition audit table

Revision ID: 0005_lead_state_transitions
Revises: 0004_lead_quality_and_fraud
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0005_lead_state_transitions"
down_revision = "0004_lead_quality_and_fraud"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_state_transitions (
            id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES leads(id),
            from_state varchar(32) NOT NULL,
            to_state varchar(32) NOT NULL,
            event_type varchar(64) NOT NULL,
            idempotency_key varchar(128) NOT NULL,
            payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_lead_state_transitions_idempotency_key UNIQUE (idempotency_key)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_state_transitions_lead_id ON lead_state_transitions(lead_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_state_transitions_event_type ON lead_state_transitions(event_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_state_transitions_created_at ON lead_state_transitions(created_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_state_transitions_to_state ON lead_state_transitions(to_state);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_state_transitions_lead_created_at ON lead_state_transitions(lead_id, created_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_lead_state_transitions_lead_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_lead_state_transitions_to_state;")
    op.execute("DROP INDEX IF EXISTS ix_lead_state_transitions_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_lead_state_transitions_event_type;")
    op.execute("DROP INDEX IF EXISTS ix_lead_state_transitions_lead_id;")
    op.execute("DROP TABLE IF EXISTS lead_state_transitions;")
