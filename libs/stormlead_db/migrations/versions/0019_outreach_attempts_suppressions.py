"""add outreach attempts and channel suppressions

Revision ID: 0019_outreach_attempts_suppressions
Revises: 0018_payment_customer_autorefill
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_outreach_attempts_suppressions"
down_revision = "0018_payment_customer_autorefill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="outbound"),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="recorded"),
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
            "channel IN ('sms', 'email', 'voice')", name="ck_outreach_attempts_channel"
        ),
        sa.CheckConstraint(
            "direction IN ('outbound', 'inbound')", name="ck_outreach_attempts_direction"
        ),
        sa.CheckConstraint(
            "status IN ('recorded', 'queued', 'sent', 'delivered', 'received', 'failed', 'blocked')",
            name="ck_outreach_attempts_status",
        ),
        sa.CheckConstraint(
            "status != 'queued' OR idempotency_key IS NOT NULL",
            name="ck_outreach_attempts_queued_has_idempotency",
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outreach_attempts_buyer_id", "outreach_attempts", ["buyer_id"])
    op.create_index("ix_outreach_attempts_channel", "outreach_attempts", ["channel"])
    op.create_index("ix_outreach_attempts_created_at", "outreach_attempts", ["created_at"])
    op.create_index("ix_outreach_attempts_direction", "outreach_attempts", ["direction"])
    op.create_index("ix_outreach_attempts_lead_id", "outreach_attempts", ["lead_id"])
    op.create_index(
        "ix_outreach_attempts_lead_created_at",
        "outreach_attempts",
        ["lead_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_outreach_attempts_provider", "outreach_attempts", ["provider"])
    op.create_index("ix_outreach_attempts_status", "outreach_attempts", ["status"])
    op.create_index(
        "uq_outreach_attempts_provider_message",
        "outreach_attempts",
        ["provider", "external_message_id"],
        unique=True,
        postgresql_where=sa.text("provider IS NOT NULL AND external_message_id IS NOT NULL"),
    )
    op.create_index(
        "uq_outreach_attempts_idempotency_key",
        "outreach_attempts",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "channel_suppressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("phone_e164", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("reason", sa.String(length=64), nullable=False, server_default="opt_out"),
        sa.Column("source_provider", sa.String(length=32), nullable=True),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
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
            "channel IN ('sms', 'email', 'voice')", name="ck_channel_suppressions_channel"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name="ck_channel_suppressions_status"
        ),
        sa.CheckConstraint(
            "phone_e164 IS NOT NULL OR email IS NOT NULL",
            name="ck_channel_suppressions_contact_present",
        ),
        sa.CheckConstraint(
            "((channel IN ('sms', 'voice') AND phone_e164 IS NOT NULL) "
            "OR (channel = 'email' AND email IS NOT NULL))",
            name="ck_channel_suppressions_channel_contact_match",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_channel_suppressions_channel", "channel_suppressions", ["channel"])
    op.create_index("ix_channel_suppressions_created_at", "channel_suppressions", ["created_at"])
    op.create_index("ix_channel_suppressions_email", "channel_suppressions", ["email"])
    op.create_index("ix_channel_suppressions_phone_e164", "channel_suppressions", ["phone_e164"])
    op.create_index("ix_channel_suppressions_reason", "channel_suppressions", ["reason"])
    op.create_index("ix_channel_suppressions_status", "channel_suppressions", ["status"])
    op.create_index(
        "uq_channel_suppressions_active_email",
        "channel_suppressions",
        ["channel", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND email IS NOT NULL"),
    )
    op.create_index(
        "uq_channel_suppressions_active_phone",
        "channel_suppressions",
        ["channel", "phone_e164"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND phone_e164 IS NOT NULL"),
    )
    op.create_index(
        "uq_channel_suppressions_provider_event",
        "channel_suppressions",
        ["channel", "source_provider", "external_event_id"],
        unique=True,
        postgresql_where=sa.text("source_provider IS NOT NULL AND external_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_channel_suppressions_provider_event", table_name="channel_suppressions")
    op.drop_index("uq_channel_suppressions_active_phone", table_name="channel_suppressions")
    op.drop_index("uq_channel_suppressions_active_email", table_name="channel_suppressions")
    op.drop_index("ix_channel_suppressions_status", table_name="channel_suppressions")
    op.drop_index("ix_channel_suppressions_reason", table_name="channel_suppressions")
    op.drop_index("ix_channel_suppressions_phone_e164", table_name="channel_suppressions")
    op.drop_index("ix_channel_suppressions_email", table_name="channel_suppressions")
    op.drop_index("ix_channel_suppressions_created_at", table_name="channel_suppressions")
    op.drop_index("ix_channel_suppressions_channel", table_name="channel_suppressions")
    op.drop_table("channel_suppressions")
    op.drop_index("uq_outreach_attempts_idempotency_key", table_name="outreach_attempts")
    op.drop_index("uq_outreach_attempts_provider_message", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_status", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_provider", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_lead_created_at", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_lead_id", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_direction", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_created_at", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_channel", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_buyer_id", table_name="outreach_attempts")
    op.drop_table("outreach_attempts")
