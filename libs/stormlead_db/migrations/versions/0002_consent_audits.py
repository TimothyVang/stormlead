"""add consent_audits table for tcpa-defensible audit trail

mirrors the ConsentAudit sqlalchemy model in stormlead_db.tables.
written as raw `CREATE TABLE IF NOT EXISTS` so it's safe to apply
after a `Base.metadata.create_all` in dev (the same pattern as 0001).

Revision ID: 0002_consent_audits
Revises: 0001_initial
Create Date: 2026-05-02

"""
from __future__ import annotations

from alembic import op


revision = "0002_consent_audits"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS consent_audits (
            webhook_id              text PRIMARY KEY,
            lead_id                 uuid NOT NULL REFERENCES leads(id),
            received_at             timestamptz NOT NULL DEFAULT now(),
            formbricks_response_id  text NOT NULL,
            page_url                text NOT NULL,
            ip                      varchar(45) NOT NULL,
            user_agent              text NOT NULL,
            consent_text            text NOT NULL,
            page_html_sha256        varchar(64),
            dwell_ms                integer,
            raw_payload             jsonb NOT NULL
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_consent_audits_lead
        ON consent_audits(lead_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_consent_audits_lead;")
    op.execute("DROP TABLE IF EXISTS consent_audits;")
