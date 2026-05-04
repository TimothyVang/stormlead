"""add lead quality/fraud fields

Revision ID: 0004_lead_quality_and_fraud
Revises: 0003_paid_pilot_fields
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0004_lead_quality_and_fraud"
down_revision = "0003_paid_pilot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS score double precision;")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS score_reason text;")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS hold_for_review boolean NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS blocked_for_fraud boolean NOT NULL DEFAULT false;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_hold_for_review ON leads(hold_for_review);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_blocked_for_fraud ON leads(blocked_for_fraud);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_leads_blocked_for_fraud;")
    op.execute("DROP INDEX IF EXISTS ix_leads_hold_for_review;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS blocked_for_fraud;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS hold_for_review;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS score_reason;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS score;")
