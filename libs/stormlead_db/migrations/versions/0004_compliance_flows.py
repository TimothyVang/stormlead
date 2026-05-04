"""compliance suppression, disclosure logs, and consent hash

Revision ID: 0004_compliance_flows
Revises: 0003_paid_pilot_fields
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0004_compliance_flows"
down_revision = "0003_paid_pilot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS consent_version_hash varchar(64) NOT NULL DEFAULT '';")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS suppressions (
          id uuid PRIMARY KEY,
          phone_e164 varchar(20),
          email varchar(255),
          lead_id uuid REFERENCES leads(id),
          reason varchar(64) NOT NULL DEFAULT 'opt_out',
          source_channel varchar(32) NOT NULL,
          source_detail text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_suppressions_identity CHECK (phone_e164 IS NOT NULL OR email IS NOT NULL OR lead_id IS NOT NULL)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_suppressions_phone_e164 ON suppressions(phone_e164);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_suppressions_email ON suppressions(email);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_suppressions_lead_id ON suppressions(lead_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_suppressions_source_channel ON suppressions(source_channel);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS disclosure_logs (
          id uuid PRIMARY KEY,
          lead_id uuid NOT NULL REFERENCES leads(id),
          recipient_type varchar(32) NOT NULL,
          recipient_id varchar(128) NOT NULL,
          recipient_name varchar(255),
          channel varchar(32) NOT NULL,
          disclosed_at timestamptz NOT NULL DEFAULT now(),
          metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_disclosure_logs_lead_id ON disclosure_logs(lead_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_disclosure_logs_recipient_id ON disclosure_logs(recipient_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_disclosure_logs_channel ON disclosure_logs(channel);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS disclosure_logs;")
    op.execute("DROP TABLE IF EXISTS suppressions;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS consent_version_hash;")
