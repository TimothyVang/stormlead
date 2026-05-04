"""add lead lifecycle state and transition timestamps

Revision ID: 0004_lead_lifecycle
Revises: 0003_paid_pilot_fields
Create Date: 2026-05-04

"""

from __future__ import annotations

from alembic import op

revision = "0004_lead_lifecycle"
down_revision = "0003_paid_pilot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS lifecycle_state varchar(32) NOT NULL DEFAULT 'captured';")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS lifecycle_transitioned_at timestamptz NOT NULL DEFAULT now();")
    for col in [
        "captured_at",
        "qualified_a_at",
        "qualified_b_at",
        "qualified_c_at",
        "qualified_d_at",
        "auctioned_at",
        "sold_at",
        "unsold_at",
        "returned_at",
        "credited_at",
        "suppressed_at",
    ]:
        op.execute(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} timestamptz;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_lifecycle_state ON leads(lifecycle_state);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_leads_lifecycle_state;")
    for col in [
        "suppressed_at",
        "credited_at",
        "returned_at",
        "unsold_at",
        "sold_at",
        "auctioned_at",
        "qualified_d_at",
        "qualified_c_at",
        "qualified_b_at",
        "qualified_a_at",
        "captured_at",
        "lifecycle_transitioned_at",
        "lifecycle_state",
    ]:
        op.execute(f"ALTER TABLE leads DROP COLUMN IF EXISTS {col};")
