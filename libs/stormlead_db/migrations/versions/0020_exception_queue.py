"""add durable exception queue

Revision ID: 0020_exception_queue
Revises: 0019_outreach_attempts_suppressions
Create Date: 2026-05-13
"""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_exception_queue"
down_revision = "0019_outreach_attempts_suppressions"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return bool(inspector.has_table(table))


def _index_exists(table: str, index: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return any(existing["name"] == index for existing in inspector.get_indexes(table))


def upgrade() -> None:
    if not _table_exists("exception_queue"):
        op.create_table(
            "exception_queue",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("owner", sa.String(length=128), nullable=True),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("buyer_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("return_request_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("post_result_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("reason", sa.String(length=128), nullable=False),
            sa.Column("recommended_action", sa.Text(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "severity IN ('critical', 'warning', 'info')",
                name="ck_exception_queue_severity",
            ),
            sa.CheckConstraint(
                "status IN ('open', 'in_progress', 'resolved', 'dismissed')",
                name="ck_exception_queue_status",
            ),
            sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
            sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
            sa.ForeignKeyConstraint(["post_result_id"], ["post_results.id"]),
            sa.ForeignKeyConstraint(["return_request_id"], ["return_requests.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("exception_queue", "ix_exception_queue_buyer_id"):
        op.create_index("ix_exception_queue_buyer_id", "exception_queue", ["buyer_id"])
    if not _index_exists("exception_queue", "ix_exception_queue_created_at"):
        op.create_index("ix_exception_queue_created_at", "exception_queue", ["created_at"])
    if not _index_exists("exception_queue", "ix_exception_queue_entity_type"):
        op.create_index("ix_exception_queue_entity_type", "exception_queue", ["entity_type"])
    if not _index_exists("exception_queue", "ix_exception_queue_kind"):
        op.create_index("ix_exception_queue_kind", "exception_queue", ["kind"])
    if not _index_exists("exception_queue", "ix_exception_queue_lead_id"):
        op.create_index("ix_exception_queue_lead_id", "exception_queue", ["lead_id"])
    if not _index_exists("exception_queue", "ix_exception_queue_owner"):
        op.create_index("ix_exception_queue_owner", "exception_queue", ["owner"])
    if not _index_exists("exception_queue", "ix_exception_queue_post_result_id"):
        op.create_index("ix_exception_queue_post_result_id", "exception_queue", ["post_result_id"])
    if not _index_exists("exception_queue", "ix_exception_queue_reason"):
        op.create_index("ix_exception_queue_reason", "exception_queue", ["reason"])
    if not _index_exists("exception_queue", "ix_exception_queue_return_request_id"):
        op.create_index(
            "ix_exception_queue_return_request_id",
            "exception_queue",
            ["return_request_id"],
        )
    if not _index_exists("exception_queue", "ix_exception_queue_severity"):
        op.create_index("ix_exception_queue_severity", "exception_queue", ["severity"])
    if not _index_exists("exception_queue", "ix_exception_queue_status"):
        op.create_index("ix_exception_queue_status", "exception_queue", ["status"])
    if not _index_exists("exception_queue", "ix_exception_queue_status_severity_sla"):
        op.create_index(
            "ix_exception_queue_status_severity_sla",
            "exception_queue",
            ["status", "severity", "sla_due_at"],
        )
    if not _index_exists("exception_queue", "uq_exception_queue_idempotency_key"):
        op.create_index(
            "uq_exception_queue_idempotency_key",
            "exception_queue",
            ["idempotency_key"],
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )


def downgrade() -> None:
    op.drop_index("uq_exception_queue_idempotency_key", table_name="exception_queue")
    op.drop_index("ix_exception_queue_status_severity_sla", table_name="exception_queue")
    op.drop_index("ix_exception_queue_status", table_name="exception_queue")
    op.drop_index("ix_exception_queue_severity", table_name="exception_queue")
    op.drop_index("ix_exception_queue_return_request_id", table_name="exception_queue")
    op.drop_index("ix_exception_queue_reason", table_name="exception_queue")
    op.drop_index("ix_exception_queue_post_result_id", table_name="exception_queue")
    op.drop_index("ix_exception_queue_owner", table_name="exception_queue")
    op.drop_index("ix_exception_queue_lead_id", table_name="exception_queue")
    op.drop_index("ix_exception_queue_kind", table_name="exception_queue")
    op.drop_index("ix_exception_queue_entity_type", table_name="exception_queue")
    op.drop_index("ix_exception_queue_created_at", table_name="exception_queue")
    op.drop_index("ix_exception_queue_buyer_id", table_name="exception_queue")
    op.drop_table("exception_queue")
