"""add billing event external event id

Revision ID: 0016_billing_event_external_event_id
Revises: 0015_structured_damage_review
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0016_billing_event_external_event_id"
down_revision = "0015_structured_damage_review"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return any(existing["name"] == column for existing in inspector.get_columns(table))


def _index_exists(table: str, index: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return any(existing["name"] == index for existing in inspector.get_indexes(table))


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
    )
    if not _column_exists("billing_events", "external_event_id"):
        op.add_column(
            "billing_events", sa.Column("external_event_id", sa.String(length=255), nullable=True)
        )
    if not _index_exists("billing_events", "ix_billing_events_external_event_id"):
        op.create_index(
            "ix_billing_events_external_event_id",
            "billing_events",
            ["external_event_id"],
            postgresql_where=sa.text("external_event_id IS NOT NULL"),
        )


def downgrade() -> None:
    op.drop_index("ix_billing_events_external_event_id", table_name="billing_events")
    op.drop_column("billing_events", "external_event_id")
