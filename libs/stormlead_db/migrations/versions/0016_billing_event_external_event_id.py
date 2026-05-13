"""add billing event external event id

Revision ID: 0016_billing_event_external_event_id
Revises: 0015_structured_damage_review
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_billing_event_external_event_id"
down_revision = "0015_structured_damage_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "billing_events", sa.Column("external_event_id", sa.String(length=255), nullable=True)
    )
    op.create_index(
        "uq_billing_events_external_event_id",
        "billing_events",
        ["external_event_id"],
        unique=True,
        postgresql_where=sa.text("external_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_billing_events_external_event_id", table_name="billing_events")
    op.drop_column("billing_events", "external_event_id")
