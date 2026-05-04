"""add agent run/session/event artifact tables

Revision ID: 0005_agent_run_tables
Revises: 0004_lead_quality_and_fraud
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0005_agent_run_tables"
down_revision = "0004_lead_quality_and_fraud"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_sessions (
            run_id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES leads(id),
            status varchar(32) NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz NULL,
            assignee varchar(255) NULL,
            escalation_reason text NULL,
            retry_count integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_steps (
            step_id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES run_sessions(run_id) ON DELETE CASCADE,
            step_type varchar(64) NOT NULL,
            status varchar(32) NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz NULL,
            error_code varchar(64) NULL,
            error_message text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_events (
            event_id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES run_sessions(run_id) ON DELETE CASCADE,
            step_id uuid NULL REFERENCES run_steps(step_id) ON DELETE SET NULL,
            event_type varchar(64) NOT NULL,
            payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            ts timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_artifacts (
            artifact_id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES run_sessions(run_id) ON DELETE CASCADE,
            step_id uuid NULL REFERENCES run_steps(step_id) ON DELETE SET NULL,
            artifact_type varchar(64) NOT NULL,
            uri text NOT NULL,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            ts timestamptz NOT NULL DEFAULT now()
        );
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_run_sessions_lead_id ON run_sessions(lead_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_sessions_status ON run_sessions(status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_steps_run_id ON run_steps(run_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_steps_status ON run_steps(status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_events_run_id ON run_events(run_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_events_step_id ON run_events(step_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_events_event_type ON run_events(event_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_events_ts ON run_events(ts);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_artifacts_run_id ON run_artifacts(run_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_artifacts_step_id ON run_artifacts(step_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_artifacts_type ON run_artifacts(artifact_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_run_artifacts_ts ON run_artifacts(ts);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_run_artifacts_ts;")
    op.execute("DROP INDEX IF EXISTS ix_run_artifacts_type;")
    op.execute("DROP INDEX IF EXISTS ix_run_artifacts_step_id;")
    op.execute("DROP INDEX IF EXISTS ix_run_artifacts_run_id;")
    op.execute("DROP INDEX IF EXISTS ix_run_events_ts;")
    op.execute("DROP INDEX IF EXISTS ix_run_events_event_type;")
    op.execute("DROP INDEX IF EXISTS ix_run_events_step_id;")
    op.execute("DROP INDEX IF EXISTS ix_run_events_run_id;")
    op.execute("DROP INDEX IF EXISTS ix_run_steps_status;")
    op.execute("DROP INDEX IF EXISTS ix_run_steps_run_id;")
    op.execute("DROP INDEX IF EXISTS ix_run_sessions_status;")
    op.execute("DROP INDEX IF EXISTS ix_run_sessions_lead_id;")

    op.execute("DROP TABLE IF EXISTS run_artifacts;")
    op.execute("DROP TABLE IF EXISTS run_events;")
    op.execute("DROP TABLE IF EXISTS run_steps;")
    op.execute("DROP TABLE IF EXISTS run_sessions;")
