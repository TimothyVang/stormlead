"""add suppression/dnc/compliance logs and buyer jurisdiction metadata

Revision ID: 0004_compliance_controls
Revises: 0003_paid_pilot_fields
Create Date: 2026-05-04

"""

from __future__ import annotations

from alembic import op

revision = "0004_compliance_controls"
down_revision = "0003_paid_pilot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE buyers ADD COLUMN IF NOT EXISTS license_jurisdiction_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS suppression_entries (
            id uuid PRIMARY KEY,
            phone_e164 varchar(20),
            email varchar(255),
            source varchar(64) NOT NULL DEFAULT 'manual',
            reason text,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_suppression_entries_phone_e164 ON suppression_entries(phone_e164);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_suppression_entries_email ON suppression_entries(email);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dnc_entries (
            id uuid PRIMARY KEY,
            phone_e164 varchar(20) NOT NULL,
            source varchar(64) NOT NULL DEFAULT 'manual',
            reason text,
            active boolean NOT NULL DEFAULT true,
            expires_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_dnc_entries_phone_e164 ON dnc_entries(phone_e164);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS compliance_decision_logs (
            id uuid PRIMARY KEY,
            actor varchar(128) NOT NULL,
            action varchar(128) NOT NULL,
            lead_id uuid REFERENCES leads(id),
            buyer_id uuid REFERENCES buyers(id),
            blocked boolean NOT NULL DEFAULT false,
            rule_hit varchar(128),
            details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_compliance_decision_logs_actor ON compliance_decision_logs(actor);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS compliance_decision_logs;")
    op.execute("DROP TABLE IF EXISTS dnc_entries;")
    op.execute("DROP TABLE IF EXISTS suppression_entries;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS license_jurisdiction_metadata;")
