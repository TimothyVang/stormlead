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
    # NOTE (2026-05-02): this revision is currently a no-op for dev.
    #
    # the original intent was to convert ping_attempts + billing_events to
    # timescale hypertables and set up a buyer_hourly_stats continuous
    # aggregate. that requires the partition column (`created_at`) to be
    # part of every unique index — but the current models PK on `id` alone.
    # timescale rejects `create_hypertable` until either:
    #   - the PK becomes composite (id, created_at), OR
    #   - `created_at` is added to every unique index.
    #
    # at dev scale (~10s leads/day, smoke testing) hypertables are a perf
    # optimization, not correctness. plain postgres tables work. re-enable
    # the hypertable + retention + cagg ops below once the PK/index shape
    # is fixed in libs/stormlead_db/src/stormlead_db/tables.py.
    #
    # the migration runs cleanly so `alembic upgrade head` succeeds; tables
    # come from sqlalchemy.create_all (see scripts/init_db.py).
    pass

    # ------------------------------------------------------------------
    # original ops, kept commented for reference + future re-enable:
    # ------------------------------------------------------------------
    # op.execute("""
    #     SELECT create_hypertable('ping_attempts', 'created_at',
    #                              chunk_time_interval => INTERVAL '1 day',
    #                              if_not_exists => TRUE);
    # """)
    # op.execute("""
    #     SELECT create_hypertable('billing_events', 'created_at',
    #                              chunk_time_interval => INTERVAL '7 days',
    #                              if_not_exists => TRUE);
    # """)
    # op.execute("""
    #     SELECT add_retention_policy('ping_attempts', INTERVAL '180 days', if_not_exists => TRUE);
    # """)
    # op.execute("""
    #     CREATE MATERIALIZED VIEW IF NOT EXISTS buyer_hourly_stats
    #     WITH (timescaledb.continuous) AS
    #     SELECT buyer_id, time_bucket(INTERVAL '1 hour', created_at) AS bucket,
    #         COUNT(*) AS pings,
    #         COUNT(*) FILTER (WHERE accepted) AS accepts,
    #         AVG(response_ms) AS avg_response_ms,
    #         AVG(bid_cents) FILTER (WHERE accepted) AS avg_accepted_bid_cents
    #     FROM ping_attempts GROUP BY buyer_id, bucket WITH NO DATA;
    # """)
    # op.execute("""
    #     SELECT add_continuous_aggregate_policy('buyer_hourly_stats',
    #         start_offset => INTERVAL '24 hours',
    #         end_offset => INTERVAL '1 hour',
    #         schedule_interval => INTERVAL '15 minutes',
    #         if_not_exists => TRUE);
    # """)


def downgrade() -> None:
    pass  # nothing to undo while upgrade is a no-op
