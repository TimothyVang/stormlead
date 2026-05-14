"""add learning proposals

Revision ID: 0023_learning_proposals
Revises: 0022_budget_action_logs
Create Date: 2026-05-13
"""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_learning_proposals"
down_revision = "0022_budget_action_logs"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return bool(inspector.has_table(table))


def _index_exists(table: str, index: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return any(existing["name"] == index for existing in inspector.get_indexes(table))


def upgrade() -> None:
    if not _table_exists("learning_proposals"):
        op.create_table(
            "learning_proposals",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("proposal_date", sa.Date(), nullable=False),
            sa.Column("proposal_type", sa.String(length=32), nullable=False),
            sa.Column("target_area", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default="pending_replay"
            ),
            sa.Column("canary_percent", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "guardrail_metric",
                sa.String(length=64),
                nullable=False,
                server_default="conversion_rate",
            ),
            sa.Column("baseline_value", sa.Float(), nullable=True),
            sa.Column("candidate_value", sa.Float(), nullable=True),
            sa.Column(
                "rollback_threshold_pct",
                sa.Float(),
                nullable=False,
                server_default="5.0",
            ),
            sa.Column(
                "approval_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column(
                "proposal_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "replay_result_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("rollback_reason", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "proposal_type IN ('scoring_threshold', 'cadence_change', 'prompt_update')",
                name="ck_learning_proposals_type",
            ),
            sa.CheckConstraint(
                "status IN ('pending_replay', 'replay_passed', 'canary_active', "
                "'rollback_triggered', 'pending_approval', 'promoted', 'rejected')",
                name="ck_learning_proposals_status",
            ),
            sa.CheckConstraint(
                "canary_percent >= 0 AND canary_percent <= 100",
                name="ck_learning_proposals_canary_percent",
            ),
            sa.ForeignKeyConstraint(["source_proposal_id"], ["skill_proposals.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("learning_proposals", "ix_learning_proposals_approval_required"):
        op.create_index(
            "ix_learning_proposals_approval_required",
            "learning_proposals",
            ["approval_required"],
        )
    if not _index_exists("learning_proposals", "ix_learning_proposals_created_at"):
        op.create_index("ix_learning_proposals_created_at", "learning_proposals", ["created_at"])
    if not _index_exists("learning_proposals", "ix_learning_proposals_proposal_date"):
        op.create_index(
            "ix_learning_proposals_proposal_date", "learning_proposals", ["proposal_date"]
        )
    if not _index_exists("learning_proposals", "ix_learning_proposals_proposal_type"):
        op.create_index(
            "ix_learning_proposals_proposal_type", "learning_proposals", ["proposal_type"]
        )
    if not _index_exists("learning_proposals", "ix_learning_proposals_source_proposal_id"):
        op.create_index(
            "ix_learning_proposals_source_proposal_id",
            "learning_proposals",
            ["source_proposal_id"],
        )
    if not _index_exists("learning_proposals", "ix_learning_proposals_source_status"):
        op.create_index(
            "ix_learning_proposals_source_status",
            "learning_proposals",
            ["source_proposal_id", "status"],
        )
    if not _index_exists("learning_proposals", "ix_learning_proposals_status"):
        op.create_index("ix_learning_proposals_status", "learning_proposals", ["status"])
    if not _index_exists("learning_proposals", "ix_learning_proposals_status_created"):
        op.create_index(
            "ix_learning_proposals_status_created",
            "learning_proposals",
            ["status", sa.text("created_at DESC")],
        )
    if not _index_exists("learning_proposals", "ix_learning_proposals_target_area"):
        op.create_index("ix_learning_proposals_target_area", "learning_proposals", ["target_area"])
    if not _index_exists("learning_proposals", "uq_learning_proposals_idempotency_key"):
        op.create_index(
            "uq_learning_proposals_idempotency_key",
            "learning_proposals",
            ["idempotency_key"],
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )


def downgrade() -> None:
    op.drop_index("uq_learning_proposals_idempotency_key", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_target_area", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_status_created", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_status", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_source_status", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_source_proposal_id", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_proposal_type", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_proposal_date", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_created_at", table_name="learning_proposals")
    op.drop_index("ix_learning_proposals_approval_required", table_name="learning_proposals")
    op.drop_table("learning_proposals")
