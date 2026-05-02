"""initial schema + timescale hypertables

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-01

"""
from __future__ import annotations

from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tables themselves are created by `alembic revision --autogenerate` later.
    # this revision converts ping_attempts and billing_events to timescale hypertables
    # and adds default retention.
    #
    # run AFTER the autogen revision that creates the tables, OR run with
    # `alembic stamp head` to skip if already created by sqlalchemy.create_all in dev.

    op.execute(
        """
        SELECT create_hypertable('ping_attempts', 'created_at',
                                 chunk_time_interval => INTERVAL '1 day',
                                 if_not_exists => TRUE);
        """
    )
    op.execute(
        """
        SELECT create_hypertable('billing_events', 'created_at',
                                 chunk_time_interval => INTERVAL '7 days',
                                 if_not_exists => TRUE);
        """
    )

    # retention: 180 days of ping detail, billing kept forever
    op.execute(
        """
        SELECT add_retention_policy('ping_attempts', INTERVAL '180 days', if_not_exists => TRUE);
        """
    )

    # continuous aggregate: hourly buyer accept rate (drives buyer scoring)
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS buyer_hourly_stats
        WITH (timescaledb.continuous) AS
        SELECT
            buyer_id,
            time_bucket(INTERVAL '1 hour', created_at) AS bucket,
            COUNT(*) AS pings,
            COUNT(*) FILTER (WHERE accepted) AS accepts,
            AVG(response_ms) AS avg_response_ms,
            AVG(bid_cents) FILTER (WHERE accepted) AS avg_accepted_bid_cents
        FROM ping_attempts
        GROUP BY buyer_id, bucket
        WITH NO DATA;
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy('buyer_hourly_stats',
                                               start_offset => INTERVAL '24 hours',
                                               end_offset => INTERVAL '1 hour',
                                               schedule_interval => INTERVAL '15 minutes',
                                               if_not_exists => TRUE);
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS buyer_hourly_stats CASCADE;")
    # hypertables are dropped automatically when tables are dropped
