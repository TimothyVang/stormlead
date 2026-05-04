"""add agent_runs telemetry table

Revision ID: 0004_agent_runs
Revises: 0003_paid_pilot_fields
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0004_agent_runs"
down_revision = "0003_paid_pilot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            id uuid PRIMARY KEY,
            flow_name varchar(64) NOT NULL,
            workload varchar(64) NOT NULL,
            model varchar(128) NOT NULL,
            max_tokens integer NOT NULL,
            retries integer NOT NULL DEFAULT 0,
            latency_ms integer NOT NULL,
            estimated_cost_usd numeric(10,6) NOT NULL DEFAULT 0,
            outcome varchar(32) NOT NULL,
            error text,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_runs_flow_name ON agent_runs(flow_name);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_runs_workload ON agent_runs(workload);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_runs_outcome ON agent_runs(outcome);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_runs_created_at ON agent_runs(created_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_runs;")
