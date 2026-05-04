"""add return request lifecycle

Revision ID: 0004_return_requests
Revises: 0003_paid_pilot_fields
Create Date: 2026-05-04

"""

from __future__ import annotations

from alembic import op

revision = "0004_return_requests"
down_revision = "0003_paid_pilot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS return_requests (
            id uuid PRIMARY KEY,
            post_result_id uuid NOT NULL REFERENCES post_results(id),
            lead_id uuid NOT NULL REFERENCES leads(id),
            buyer_id uuid NOT NULL REFERENCES buyers(id),
            state varchar(32) NOT NULL DEFAULT 'OPEN',
            reason text NOT NULL,
            notes text,
            evidence_bundle jsonb NOT NULL DEFAULT '{}'::jsonb,
            triage_recommendation jsonb,
            reviewer_notes text,
            reviewed_by varchar(255),
            reviewed_at timestamptz,
            credited_event_id uuid REFERENCES billing_events(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_return_requests_state
                CHECK (state IN ('OPEN','UNDER_REVIEW','APPROVED','DENIED','CREDITED','ESCALATED'))
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_return_requests_post_result_id ON return_requests(post_result_id);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_return_requests_lead_id ON return_requests(lead_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_return_requests_buyer_id ON return_requests(buyer_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_return_requests_state ON return_requests(state);")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_return_requests_post_result_active
        ON return_requests(post_result_id)
        WHERE state IN ('OPEN','UNDER_REVIEW','APPROVED','ESCALATED');
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_return_requests_post_result_active;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_state;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_buyer_id;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_lead_id;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_post_result_id;")
    op.execute("DROP TABLE IF EXISTS return_requests;")
