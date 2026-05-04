"""add paid-pilot buyer and lead fields

Revision ID: 0003_paid_pilot_fields
Revises: 0002_consent_audits
Create Date: 2026-05-03

"""

from __future__ import annotations

from alembic import op

revision = "0003_paid_pilot_fields"
down_revision = "0002_consent_audits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE buyers ADD COLUMN IF NOT EXISTS sales_stage varchar(32) NOT NULL DEFAULT 'prospect';"
    )
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS notes text;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS next_follow_up_at timestamptz;")
    op.execute(
        "ALTER TABLE buyers ADD COLUMN IF NOT EXISTS services jsonb NOT NULL DEFAULT '[]'::jsonb;"
    )
    op.execute(
        "ALTER TABLE buyers ADD COLUMN IF NOT EXISTS target_zips jsonb NOT NULL DEFAULT '[]'::jsonb;"
    )
    op.execute(
        "ALTER TABLE buyers ADD COLUMN IF NOT EXISTS exclusive_zips jsonb NOT NULL DEFAULT '[]'::jsonb;"
    )
    op.execute(
        "ALTER TABLE buyers ADD COLUMN IF NOT EXISTS low_balance_threshold numeric(12, 2) NOT NULL DEFAULT 0;"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_buyers_sales_stage ON buyers(sales_stage);")

    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_class varchar(1);")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS qualification_reason text;")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS requested_service varchar(64);")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_id varchar(128);")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_source varchar(64);")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS first_touch_source varchar(64);")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_touch_source varchar(64);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_lead_class ON leads(lead_class);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_requested_service ON leads(requested_service);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_campaign_id ON leads(campaign_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_campaign_source ON leads(campaign_source);")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_leads_class'
            ) THEN
                ALTER TABLE leads ADD CONSTRAINT ck_leads_class
                CHECK (lead_class IS NULL OR lead_class IN ('a', 'b', 'c', 'd'));
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS ck_leads_class;")
    op.execute("DROP INDEX IF EXISTS ix_leads_campaign_source;")
    op.execute("DROP INDEX IF EXISTS ix_leads_campaign_id;")
    op.execute("DROP INDEX IF EXISTS ix_leads_requested_service;")
    op.execute("DROP INDEX IF EXISTS ix_leads_lead_class;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS last_touch_source;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS first_touch_source;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS campaign_source;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS campaign_id;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS requested_service;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS qualification_reason;")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS lead_class;")

    op.execute("DROP INDEX IF EXISTS ix_buyers_sales_stage;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS low_balance_threshold;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS exclusive_zips;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS target_zips;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS services;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS next_follow_up_at;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS notes;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS sales_stage;")
