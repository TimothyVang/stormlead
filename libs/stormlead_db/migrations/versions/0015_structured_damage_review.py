"""add structured damage review fields

Revision ID: 0015_structured_damage_review
Revises: 0014_consent_version
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_structured_damage_review"
down_revision = "0014_consent_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("damage_summary", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("visible_risk_level", sa.String(length=16), nullable=True))
    op.add_column("leads", sa.Column("estimated_job_size", sa.String(length=32), nullable=True))
    op.add_column("leads", sa.Column("buyer_notes", sa.Text(), nullable=True))
    op.create_index("ix_leads_visible_risk_level", "leads", ["visible_risk_level"])
    op.create_index("ix_leads_estimated_job_size", "leads", ["estimated_job_size"])


def downgrade() -> None:
    op.drop_index("ix_leads_estimated_job_size", table_name="leads")
    op.drop_index("ix_leads_visible_risk_level", table_name="leads")
    op.drop_column("leads", "buyer_notes")
    op.drop_column("leads", "estimated_job_size")
    op.drop_column("leads", "visible_risk_level")
    op.drop_column("leads", "damage_summary")
