"""add lead resale dedup

Revision ID: 0010_lead_resale_dedup
Revises: 0009_timescale_hypertables
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_lead_resale_dedup"
down_revision = "0009_timescale_hypertables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("normalized_address", sa.String(length=512), nullable=True))
    op.add_column(
        "leads",
        sa.Column("is_resale", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE leads
        SET normalized_address = regexp_replace(
            upper(concat_ws(' ', address_line1, city, state, zip)),
            '[^A-Z0-9 ]',
            '',
            'g'
        )
        WHERE normalized_address IS NULL;
        """
    )
    op.create_index("ix_leads_normalized_address", "leads", ["normalized_address"])
    op.create_index("ix_leads_is_resale", "leads", ["is_resale"])
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_lead_phone_address_storm_sellable
        ON leads (phone_e164, normalized_address, COALESCE(storm_id::text, ''))
        WHERE is_resale = false
          AND lead_class IN ('a', 'b')
          AND normalized_address IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lead_phone_address_storm_sellable;")
    op.drop_index("ix_leads_is_resale", table_name="leads")
    op.drop_index("ix_leads_normalized_address", table_name="leads")
    op.drop_column("leads", "is_resale")
    op.drop_column("leads", "normalized_address")
