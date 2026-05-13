"""add structured tree damage intake fields

Revision ID: 0013_tree_damage_intake_fields
Revises: 0012_location_photo_metadata
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_tree_damage_intake_fields"
down_revision = "0012_location_photo_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("damage_type", sa.String(length=64), nullable=True))
    op.add_column("leads", sa.Column("urgency", sa.String(length=32), nullable=True))
    op.add_column(
        "leads",
        sa.Column(
            "safety_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index("ix_leads_damage_type", "leads", ["damage_type"])
    op.create_index("ix_leads_urgency", "leads", ["urgency"])


def downgrade() -> None:
    op.drop_index("ix_leads_urgency", table_name="leads")
    op.drop_index("ix_leads_damage_type", table_name="leads")
    op.drop_column("leads", "safety_flags")
    op.drop_column("leads", "urgency")
    op.drop_column("leads", "damage_type")
