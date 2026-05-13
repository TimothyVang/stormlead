"""add budget action logs

Revision ID: 0022_budget_action_logs
Revises: 0021_campaign_spend_registry
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_budget_action_logs"
down_revision = "0021_campaign_spend_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_action_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("external_campaign_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column(
            "approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "metrics_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "decision_json",
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
            "action IN ('auto_pause', 'propose_increase', 'block_increase', 'hold')",
            name="ck_budget_action_logs_action",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'approval_required', 'applied', 'blocked', 'skipped')",
            name="ck_budget_action_logs_status",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_budget_action_logs_approval_required",
        "budget_action_logs",
        ["approval_required"],
    )
    op.create_index(
        "ix_budget_action_logs_campaign_created",
        "budget_action_logs",
        ["campaign_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_budget_action_logs_action", "budget_action_logs", ["action"])
    op.create_index("ix_budget_action_logs_created_at", "budget_action_logs", ["created_at"])
    op.create_index(
        "ix_budget_action_logs_external_campaign_id",
        "budget_action_logs",
        ["external_campaign_id"],
    )
    op.create_index("ix_budget_action_logs_platform", "budget_action_logs", ["platform"])
    op.create_index("ix_budget_action_logs_status", "budget_action_logs", ["status"])
    op.create_index(
        "uq_budget_action_logs_idempotency_key",
        "budget_action_logs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_budget_action_logs_idempotency_key", table_name="budget_action_logs")
    op.drop_index("ix_budget_action_logs_status", table_name="budget_action_logs")
    op.drop_index("ix_budget_action_logs_platform", table_name="budget_action_logs")
    op.drop_index(
        "ix_budget_action_logs_external_campaign_id",
        table_name="budget_action_logs",
    )
    op.drop_index("ix_budget_action_logs_created_at", table_name="budget_action_logs")
    op.drop_index("ix_budget_action_logs_action", table_name="budget_action_logs")
    op.drop_index("ix_budget_action_logs_campaign_created", table_name="budget_action_logs")
    op.drop_index("ix_budget_action_logs_approval_required", table_name="budget_action_logs")
    op.drop_table("budget_action_logs")
