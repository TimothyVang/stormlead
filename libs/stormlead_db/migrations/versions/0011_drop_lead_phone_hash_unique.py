"""add capture idempotency and drop phone/page hash uniqueness

Revision ID: 0011_drop_lead_phone_hash_unique
Revises: 0010_lead_resale_dedup
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_drop_lead_phone_hash_unique"
down_revision = "0010_lead_resale_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("capture_webhook_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("capture_event_emitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "capture_event_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "leads",
        sa.Column("capture_event_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_leads_capture_webhook_id",
        "leads",
        ["capture_webhook_id"],
        unique=True,
        postgresql_where=sa.text("capture_webhook_id IS NOT NULL"),
    )
    op.execute(sa.text("ALTER TABLE leads DROP CONSTRAINT IF EXISTS uq_lead_phone_hash"))
    op.create_index("ix_leads_capture_event_status", "leads", ["capture_event_status"])


def downgrade() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT phone_e164, page_html_hash
            FROM leads
            GROUP BY phone_e164, page_html_hash
            HAVING COUNT(*) > 1
            LIMIT 1
            """
            )
        )
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(
            "Cannot downgrade 0011_drop_lead_phone_hash_unique while duplicate "
            "(phone_e164, page_html_hash) rows exist. Deduplicate leads first."
        )

    op.create_unique_constraint(
        "uq_lead_phone_hash",
        "leads",
        ["phone_e164", "page_html_hash"],
    )
    op.drop_index("ix_leads_capture_event_status", table_name="leads")
    op.drop_index("uq_leads_capture_webhook_id", table_name="leads")
    op.drop_column("leads", "capture_event_claimed_at")
    op.drop_column("leads", "capture_event_status")
    op.drop_column("leads", "capture_event_emitted_at")
    op.drop_column("leads", "capture_webhook_id")
