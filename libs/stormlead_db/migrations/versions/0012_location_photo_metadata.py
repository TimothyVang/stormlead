"""add lead location and photo metadata

Revision ID: 0012_location_photo_metadata
Revises: 0011_drop_lead_phone_hash_unique
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_location_photo_metadata"
down_revision = "0011_drop_lead_phone_hash_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("google_click_id", sa.String(length=128), nullable=True))
    op.add_column("leads", sa.Column("gps_latitude", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("gps_longitude", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("gps_accuracy_meters", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("gps_captured_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("location_source", sa.String(length=32), nullable=True))
    op.add_column(
        "leads", sa.Column("location_confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "leads", sa.Column("location_verification_status", sa.String(length=32), nullable=True)
    )
    op.create_index("ix_leads_google_click_id", "leads", ["google_click_id"])
    op.create_index(
        "ix_leads_location_verification_status", "leads", ["location_verification_status"]
    )


def downgrade() -> None:
    op.drop_index("ix_leads_location_verification_status", table_name="leads")
    op.drop_index("ix_leads_google_click_id", table_name="leads")
    op.drop_column("leads", "location_verification_status")
    op.drop_column("leads", "location_confirmed_at")
    op.drop_column("leads", "location_source")
    op.drop_column("leads", "gps_captured_at")
    op.drop_column("leads", "gps_accuracy_meters")
    op.drop_column("leads", "gps_longitude")
    op.drop_column("leads", "gps_latitude")
    op.drop_column("leads", "google_click_id")
