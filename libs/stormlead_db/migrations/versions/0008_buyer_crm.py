"""add buyer crm fields and call events table

Revision ID: 0008_buyer_crm
Revises: 0007_skill_proposals
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0008_buyer_crm"
down_revision = "0007_skill_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS api_key varchar(128);")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS sales_stage varchar(32) NOT NULL DEFAULT 'prospect';")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS services_offered jsonb NOT NULL DEFAULT '[]'::jsonb;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS notes text;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS follow_up_date timestamptz;")
    op.execute("ALTER TABLE buyers ADD COLUMN IF NOT EXISTS low_balance_threshold_cents bigint NOT NULL DEFAULT 10000;")
    op.execute("UPDATE buyers SET services_offered = services WHERE services_offered = '[]'::jsonb AND services IS NOT NULL;")
    op.execute("UPDATE buyers SET follow_up_date = next_follow_up_at WHERE follow_up_date IS NULL AND next_follow_up_at IS NOT NULL;")
    op.execute("UPDATE buyers SET low_balance_threshold_cents = (low_balance_threshold * 100)::bigint WHERE low_balance_threshold IS NOT NULL;")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_buyers_api_key ON buyers(api_key) WHERE api_key IS NOT NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_buyers_sales_stage ON buyers(sales_stage);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_buyers_follow_up_date ON buyers(follow_up_date);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS call_events (
            id uuid PRIMARY KEY,
            call_id varchar(128) NOT NULL UNIQUE,
            lead_id uuid REFERENCES leads(id),
            phone_e164 varchar(20) NOT NULL,
            duration_seconds integer,
            outcome varchar(32) NOT NULL,
            tracked_at timestamptz NOT NULL,
            raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_call_events_outcome
                CHECK (outcome IN ('answered', 'voicemail', 'no_answer', 'busy'))
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_call_events_call_id ON call_events(call_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_call_events_lead_id ON call_events(lead_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_call_events_phone_e164 ON call_events(phone_e164);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_call_events_outcome ON call_events(outcome);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_call_events_tracked_at ON call_events(tracked_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_call_events_created_at ON call_events(created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_call_events_lead_tracked_at ON call_events(lead_id, tracked_at DESC);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_call_events_lead_tracked_at;")
    op.execute("DROP INDEX IF EXISTS ix_call_events_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_call_events_tracked_at;")
    op.execute("DROP INDEX IF EXISTS ix_call_events_outcome;")
    op.execute("DROP INDEX IF EXISTS ix_call_events_phone_e164;")
    op.execute("DROP INDEX IF EXISTS ix_call_events_lead_id;")
    op.execute("DROP INDEX IF EXISTS ix_call_events_call_id;")
    op.execute("DROP TABLE IF EXISTS call_events;")
    op.execute("DROP INDEX IF EXISTS ix_buyers_follow_up_date;")
    op.execute("DROP INDEX IF EXISTS ix_buyers_sales_stage;")
    op.execute("DROP INDEX IF EXISTS ix_buyers_api_key;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS low_balance_threshold_cents;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS follow_up_date;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS services_offered;")
    op.execute("ALTER TABLE buyers DROP COLUMN IF EXISTS api_key;")
