"""add campaign spend registry

Revision ID: 0021_campaign_spend_registry
Revises: 0020_exception_queue
Create Date: 2026-05-13
"""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_campaign_spend_registry"
down_revision = "0020_exception_queue"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return bool(inspector.has_table(table))


def _index_exists(table: str, index: str) -> bool:
    inspector = cast(Any, sa.inspect(op.get_bind()))
    return any(existing["name"] == index for existing in inspector.get_indexes(table))


def upgrade() -> None:
    if not _table_exists("campaigns"):
        op.create_table(
            "campaigns",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("external_campaign_id", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("service", sa.String(length=64), nullable=True),
            sa.Column("market_state", sa.String(length=2), nullable=True),
            sa.Column(
                "target_zips",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("daily_budget_cents", sa.BigInteger(), nullable=True),
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
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "daily_budget_cents IS NULL OR daily_budget_cents >= 0",
                name="ck_campaigns_daily_budget_nonnegative",
            ),
            sa.CheckConstraint(
                "platform IN ('local', 'google_ads', 'meta', 'microsoft_ads')",
                name="ck_campaigns_platform",
            ),
            sa.CheckConstraint(
                "status IN ('draft', 'active', 'paused', 'archived')",
                name="ck_campaigns_status",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "platform",
                "external_campaign_id",
                name="uq_campaigns_platform_external_campaign_id",
            ),
        )
    if not _index_exists("campaigns", "ix_campaigns_external_campaign_id"):
        op.create_index("ix_campaigns_external_campaign_id", "campaigns", ["external_campaign_id"])
    if not _index_exists("campaigns", "ix_campaigns_market_state"):
        op.create_index("ix_campaigns_market_state", "campaigns", ["market_state"])
    if not _index_exists("campaigns", "ix_campaigns_platform"):
        op.create_index("ix_campaigns_platform", "campaigns", ["platform"])
    if not _index_exists("campaigns", "ix_campaigns_service"):
        op.create_index("ix_campaigns_service", "campaigns", ["service"])
    if not _index_exists("campaigns", "ix_campaigns_status"):
        op.create_index("ix_campaigns_status", "campaigns", ["status"])

    if not _table_exists("campaign_spend_snapshots"):
        op.create_table(
            "campaign_spend_snapshots",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("external_campaign_id", sa.String(length=128), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("spend_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="local"),
            sa.Column(
                "payload_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "ingested_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint("clicks >= 0", name="ck_campaign_spend_clicks_nonnegative"),
            sa.CheckConstraint(
                "conversions >= 0",
                name="ck_campaign_spend_conversions_nonnegative",
            ),
            sa.CheckConstraint(
                "impressions >= 0",
                name="ck_campaign_spend_impressions_nonnegative",
            ),
            sa.CheckConstraint("spend_cents >= 0", name="ck_campaign_spend_nonnegative"),
            sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "platform",
                "external_campaign_id",
                "snapshot_date",
                name="uq_campaign_spend_platform_campaign_date",
            ),
        )
    if not _index_exists("campaign_spend_snapshots", "ix_campaign_spend_campaign_date"):
        op.create_index(
            "ix_campaign_spend_campaign_date",
            "campaign_spend_snapshots",
            ["campaign_id", sa.text("snapshot_date DESC")],
        )
    if not _index_exists(
        "campaign_spend_snapshots", "ix_campaign_spend_snapshots_external_campaign_id"
    ):
        op.create_index(
            "ix_campaign_spend_snapshots_external_campaign_id",
            "campaign_spend_snapshots",
            ["external_campaign_id"],
        )
    if not _index_exists("campaign_spend_snapshots", "ix_campaign_spend_snapshots_ingested_at"):
        op.create_index(
            "ix_campaign_spend_snapshots_ingested_at",
            "campaign_spend_snapshots",
            ["ingested_at"],
        )
    if not _index_exists("campaign_spend_snapshots", "ix_campaign_spend_snapshots_platform"):
        op.create_index(
            "ix_campaign_spend_snapshots_platform",
            "campaign_spend_snapshots",
            ["platform"],
        )
    if not _index_exists("campaign_spend_snapshots", "ix_campaign_spend_snapshots_snapshot_date"):
        op.create_index(
            "ix_campaign_spend_snapshots_snapshot_date",
            "campaign_spend_snapshots",
            ["snapshot_date"],
        )
    if not _index_exists("campaign_spend_snapshots", "ix_campaign_spend_snapshots_source"):
        op.create_index(
            "ix_campaign_spend_snapshots_source",
            "campaign_spend_snapshots",
            ["source"],
        )

    if not _table_exists("tracking_links"):
        op.create_table(
            "tracking_links",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("medium", sa.String(length=64), nullable=False),
            sa.Column("campaign_slug", sa.String(length=128), nullable=False),
            sa.Column("destination_url", sa.Text(), nullable=False),
            sa.Column("tracking_url", sa.Text(), nullable=False),
            sa.Column("utm_source", sa.String(length=64), nullable=False),
            sa.Column("utm_medium", sa.String(length=64), nullable=False),
            sa.Column("utm_campaign", sa.String(length=128), nullable=False),
            sa.Column("click_id_param", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
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
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('active', 'paused', 'archived')",
                name="ck_tracking_links_status",
            ),
            sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tracking_url", name="uq_tracking_links_tracking_url"),
        )
    if not _index_exists("tracking_links", "ix_tracking_links_campaign_status"):
        op.create_index(
            "ix_tracking_links_campaign_status",
            "tracking_links",
            ["campaign_id", "status"],
        )
    if not _index_exists("tracking_links", "ix_tracking_links_campaign_slug"):
        op.create_index("ix_tracking_links_campaign_slug", "tracking_links", ["campaign_slug"])
    if not _index_exists("tracking_links", "ix_tracking_links_medium"):
        op.create_index("ix_tracking_links_medium", "tracking_links", ["medium"])
    if not _index_exists("tracking_links", "ix_tracking_links_source"):
        op.create_index("ix_tracking_links_source", "tracking_links", ["source"])
    if not _index_exists("tracking_links", "ix_tracking_links_status"):
        op.create_index("ix_tracking_links_status", "tracking_links", ["status"])
    if not _index_exists("tracking_links", "ix_tracking_links_utm_campaign"):
        op.create_index("ix_tracking_links_utm_campaign", "tracking_links", ["utm_campaign"])
    if not _index_exists("tracking_links", "ix_tracking_links_utm_medium"):
        op.create_index("ix_tracking_links_utm_medium", "tracking_links", ["utm_medium"])
    if not _index_exists("tracking_links", "ix_tracking_links_utm_source"):
        op.create_index("ix_tracking_links_utm_source", "tracking_links", ["utm_source"])


def downgrade() -> None:
    op.drop_index("ix_tracking_links_utm_source", table_name="tracking_links")
    op.drop_index("ix_tracking_links_utm_medium", table_name="tracking_links")
    op.drop_index("ix_tracking_links_utm_campaign", table_name="tracking_links")
    op.drop_index("ix_tracking_links_status", table_name="tracking_links")
    op.drop_index("ix_tracking_links_source", table_name="tracking_links")
    op.drop_index("ix_tracking_links_medium", table_name="tracking_links")
    op.drop_index("ix_tracking_links_campaign_slug", table_name="tracking_links")
    op.drop_index("ix_tracking_links_campaign_status", table_name="tracking_links")
    op.drop_table("tracking_links")

    op.drop_index("ix_campaign_spend_snapshots_source", table_name="campaign_spend_snapshots")
    op.drop_index(
        "ix_campaign_spend_snapshots_snapshot_date",
        table_name="campaign_spend_snapshots",
    )
    op.drop_index("ix_campaign_spend_snapshots_platform", table_name="campaign_spend_snapshots")
    op.drop_index(
        "ix_campaign_spend_snapshots_ingested_at",
        table_name="campaign_spend_snapshots",
    )
    op.drop_index(
        "ix_campaign_spend_snapshots_external_campaign_id",
        table_name="campaign_spend_snapshots",
    )
    op.drop_index("ix_campaign_spend_campaign_date", table_name="campaign_spend_snapshots")
    op.drop_table("campaign_spend_snapshots")

    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_service", table_name="campaigns")
    op.drop_index("ix_campaigns_platform", table_name="campaigns")
    op.drop_index("ix_campaigns_market_state", table_name="campaigns")
    op.drop_index("ix_campaigns_external_campaign_id", table_name="campaigns")
    op.drop_table("campaigns")
