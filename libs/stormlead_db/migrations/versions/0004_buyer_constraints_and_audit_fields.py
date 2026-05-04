"""add buyer eligibility constraints and selection audit fields

Revision ID: 0004_buyer_constraints_and_audit_fields
Revises: 0003_paid_pilot_fields
Create Date: 2026-05-04

"""

from __future__ import annotations

from alembic import op

revision = "0004_buyer_constraints_and_audit_fields"
down_revision = "0003_paid_pilot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE buyers ADD COLUMN IF NOT EXISTS zip_allowlist jsonb NOT NULL DEFAULT '[]'::jsonb;"
    )
    op.execute(
        "ALTER TABLE buyers ADD COLUMN IF NOT EXISTS zip_exclusive jsonb NOT NULL DEFAULT '[]'::jsonb;"
    )
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS monthly_cap integer;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS is_paused boolean NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS pause_ping boolean NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS pause_post boolean NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS sla_response_ms integer;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS sla_post_within_seconds integer;")

    op.execute("ALTER TABLE post_results ADD COLUMN IF NOT EXISTS selection_reason text;")
    op.execute("ALTER TABLE post_results ADD COLUMN IF NOT EXISTS selection_score integer;")


def downgrade() -> None:
    op.execute("ALTER TABLE post_results DROP COLUMN IF EXISTS selection_score;")
    op.execute("ALTER TABLE post_results DROP COLUMN IF EXISTS selection_reason;")

    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS sla_post_within_seconds;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS sla_response_ms;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS pause_post;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS pause_ping;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS is_paused;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS monthly_cap;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS zip_exclusive;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS zip_allowlist;")
