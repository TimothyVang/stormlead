"""enable timescale hypertables and retention policies

Revision ID: 0009_timescale_hypertables
Revises: 0008_buyer_crm
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0009_timescale_hypertables"
down_revision = "0008_buyer_crm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute("ALTER TABLE ping_attempts DROP CONSTRAINT IF EXISTS ping_attempts_pkey;")
    op.execute("ALTER TABLE ping_attempts ADD PRIMARY KEY (id, created_at);")
    op.execute("ALTER TABLE billing_events DROP CONSTRAINT IF EXISTS billing_events_pkey;")
    op.execute("ALTER TABLE billing_events ADD PRIMARY KEY (id, created_at);")
    op.execute(
        "SELECT create_hypertable('ping_attempts', 'created_at', if_not_exists => TRUE, migrate_data => TRUE);"
    )
    op.execute(
        "SELECT create_hypertable('billing_events', 'created_at', if_not_exists => TRUE, migrate_data => TRUE);"
    )
    op.execute(
        "SELECT add_retention_policy('ping_attempts', INTERVAL '180 days', if_not_exists => TRUE);"
    )
    op.execute(
        "SELECT add_retention_policy('billing_events', INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    # Hypertables and retention policies are intentionally not downgraded once
    # data may exist; reversing the PK/time partitioning safely is operational.
    return None
