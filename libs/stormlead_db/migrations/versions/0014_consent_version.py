"""add consent version audit fields

Revision ID: 0014_consent_version
Revises: 0013_tree_damage_intake_fields
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_consent_version"
down_revision = "0013_tree_damage_intake_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("consent_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "consent_audits",
        sa.Column("consent_version", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE leads SET consent_version = 'legacy-unknown' WHERE consent_version IS NULL")
    op.execute(
        "UPDATE consent_audits SET consent_version = 'legacy-unknown' WHERE consent_version IS NULL"
    )
    op.alter_column("leads", "consent_version", nullable=False)
    op.alter_column("consent_audits", "consent_version", nullable=False)


def downgrade() -> None:
    op.drop_column("consent_audits", "consent_version")
    op.drop_column("leads", "consent_version")
