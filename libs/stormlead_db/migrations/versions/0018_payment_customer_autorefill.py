"""add payment customers and wallet autorefill rules

Revision ID: 0018_payment_customer_autorefill
Revises: 0017_payment_webhook_events
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_payment_customer_autorefill"
down_revision = "0017_payment_webhook_events"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return bool(inspector.has_table(table))


def _index_exists(table: str, index: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return any(existing["name"] == index for existing in inspector.get_indexes(table))


def upgrade() -> None:
    if not _table_exists("payment_customers"):
        op.create_table(
            "payment_customers",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("buyer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("external_customer_id", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column(
                "metadata_json",
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
                "status IN ('pending', 'active', 'disabled')",
                name="ck_payment_customers_status",
            ),
            sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("buyer_id", "provider", name="uq_payment_customers_buyer_provider"),
            sa.UniqueConstraint(
                "provider",
                "external_customer_id",
                name="uq_payment_customers_provider_external_customer_id",
            ),
        )
    if not _index_exists("payment_customers", "ix_payment_customers_buyer_id"):
        op.create_index("ix_payment_customers_buyer_id", "payment_customers", ["buyer_id"])
    if not _index_exists("payment_customers", "ix_payment_customers_created_at"):
        op.create_index("ix_payment_customers_created_at", "payment_customers", ["created_at"])
    if not _index_exists("payment_customers", "ix_payment_customers_provider"):
        op.create_index("ix_payment_customers_provider", "payment_customers", ["provider"])
    if not _index_exists("payment_customers", "ix_payment_customers_status"):
        op.create_index("ix_payment_customers_status", "payment_customers", ["status"])

    if not _table_exists("wallet_autorefill_rules"):
        op.create_table(
            "wallet_autorefill_rules",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("buyer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="stripe"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="disabled"),
            sa.Column("threshold_cents", sa.BigInteger(), nullable=False),
            sa.Column("refill_amount_cents", sa.BigInteger(), nullable=False),
            sa.Column("daily_cap_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("monthly_cap_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column(
                "metadata_json",
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
                "status IN ('disabled', 'active', 'paused')",
                name="ck_wallet_autorefill_rules_status",
            ),
            sa.CheckConstraint("threshold_cents >= 0", name="ck_wallet_autorefill_rules_threshold"),
            sa.CheckConstraint(
                "refill_amount_cents > 0", name="ck_wallet_autorefill_rules_refill_amount"
            ),
            sa.CheckConstraint("daily_cap_cents >= 0", name="ck_wallet_autorefill_rules_daily_cap"),
            sa.CheckConstraint(
                "monthly_cap_cents >= 0", name="ck_wallet_autorefill_rules_monthly_cap"
            ),
            sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "buyer_id", "provider", name="uq_wallet_autorefill_rules_buyer_provider"
            ),
        )
    if not _index_exists("wallet_autorefill_rules", "ix_wallet_autorefill_rules_buyer_id"):
        op.create_index(
            "ix_wallet_autorefill_rules_buyer_id", "wallet_autorefill_rules", ["buyer_id"]
        )
    if not _index_exists("wallet_autorefill_rules", "ix_wallet_autorefill_rules_created_at"):
        op.create_index(
            "ix_wallet_autorefill_rules_created_at", "wallet_autorefill_rules", ["created_at"]
        )
    if not _index_exists("wallet_autorefill_rules", "ix_wallet_autorefill_rules_provider"):
        op.create_index(
            "ix_wallet_autorefill_rules_provider", "wallet_autorefill_rules", ["provider"]
        )
    if not _index_exists("wallet_autorefill_rules", "ix_wallet_autorefill_rules_status"):
        op.create_index("ix_wallet_autorefill_rules_status", "wallet_autorefill_rules", ["status"])


def downgrade() -> None:
    op.drop_index("ix_wallet_autorefill_rules_status", table_name="wallet_autorefill_rules")
    op.drop_index("ix_wallet_autorefill_rules_provider", table_name="wallet_autorefill_rules")
    op.drop_index("ix_wallet_autorefill_rules_created_at", table_name="wallet_autorefill_rules")
    op.drop_index("ix_wallet_autorefill_rules_buyer_id", table_name="wallet_autorefill_rules")
    op.drop_table("wallet_autorefill_rules")
    op.drop_index("ix_payment_customers_status", table_name="payment_customers")
    op.drop_index("ix_payment_customers_provider", table_name="payment_customers")
    op.drop_index("ix_payment_customers_created_at", table_name="payment_customers")
    op.drop_index("ix_payment_customers_buyer_id", table_name="payment_customers")
    op.drop_table("payment_customers")
