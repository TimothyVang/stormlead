"""add payment webhook event audit table

Revision ID: 0017_payment_webhook_events
Revises: 0016_billing_event_external_event_id
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_payment_webhook_events"
down_revision = "0016_billing_event_external_event_id"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return bool(inspector.has_table(table))


def _index_exists(table: str, index: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return any(existing["name"] == index for existing in inspector.get_indexes(table))


def upgrade() -> None:
    if not _table_exists("payment_webhook_events"):
        op.create_table(
            "payment_webhook_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("external_event_id", sa.String(length=255), nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
            sa.Column("payload_sha256", sa.String(length=64), nullable=False),
            sa.Column(
                "payload_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('received', 'processed', 'ignored', 'failed')",
                name="ck_payment_webhook_events_status",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "provider",
                "external_event_id",
                name="uq_payment_webhook_events_provider_external_event_id",
            ),
        )
    if not _index_exists("payment_webhook_events", "ix_payment_webhook_events_event_type"):
        op.create_index(
            "ix_payment_webhook_events_event_type",
            "payment_webhook_events",
            ["event_type"],
        )
    if not _index_exists("payment_webhook_events", "ix_payment_webhook_events_provider"):
        op.create_index(
            "ix_payment_webhook_events_provider", "payment_webhook_events", ["provider"]
        )
    if not _index_exists("payment_webhook_events", "ix_payment_webhook_events_provider_created_at"):
        op.create_index(
            "ix_payment_webhook_events_provider_created_at",
            "payment_webhook_events",
            ["provider", sa.text("created_at DESC")],
        )
    if not _index_exists("payment_webhook_events", "ix_payment_webhook_events_status"):
        op.create_index("ix_payment_webhook_events_status", "payment_webhook_events", ["status"])
    if not _index_exists("payment_webhook_events", "ix_payment_webhook_events_created_at"):
        op.create_index(
            "ix_payment_webhook_events_created_at", "payment_webhook_events", ["created_at"]
        )


def downgrade() -> None:
    op.drop_index("ix_payment_webhook_events_created_at", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_events_status", table_name="payment_webhook_events")
    op.drop_index(
        "ix_payment_webhook_events_provider_created_at", table_name="payment_webhook_events"
    )
    op.drop_index("ix_payment_webhook_events_provider", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_events_event_type", table_name="payment_webhook_events")
    op.drop_table("payment_webhook_events")
