"""add v1 paid-pilot control tables

Revision ID: 0006_v1_paid_pilot_controls
Revises: 0005_lead_state_transitions
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0006_v1_paid_pilot_controls"
down_revision = "0005_lead_state_transitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE post_results ADD COLUMN IF NOT EXISTS delivery_idempotency_key varchar(128);"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_post_results_delivery_idempotency_key
        ON post_results(delivery_idempotency_key)
        WHERE delivery_idempotency_key IS NOT NULL;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS return_requests (
            id uuid PRIMARY KEY,
            post_result_id uuid NOT NULL REFERENCES post_results(id),
            lead_id uuid NOT NULL REFERENCES leads(id),
            buyer_id uuid NOT NULL REFERENCES buyers(id),
            reason varchar(64) NOT NULL,
            notes text,
            evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            status varchar(32) NOT NULL DEFAULT 'pending_review',
            requested_by varchar(128) NOT NULL DEFAULT 'buyer',
            reviewed_by varchar(128),
            review_notes text,
            reviewed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_return_requests_status
                CHECK (status IN ('pending_review', 'held', 'approved', 'rejected'))
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_return_requests_post_result_id ON return_requests(post_result_id);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_return_requests_lead_id ON return_requests(lead_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_return_requests_buyer_id ON return_requests(buyer_id);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_return_requests_reason ON return_requests(reason);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_return_requests_status ON return_requests(status);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_return_requests_created_at ON return_requests(created_at);"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_return_requests_active_post_result
        ON return_requests(post_result_id)
        WHERE status IN ('pending_review', 'held');
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS suppression_entries (
            id uuid PRIMARY KEY,
            phone_e164 varchar(20),
            email varchar(255),
            reason varchar(128) NOT NULL DEFAULT 'consumer_opt_out',
            source varchar(64) NOT NULL DEFAULT 'privacy_request',
            status varchar(32) NOT NULL DEFAULT 'active',
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_suppression_entries_contact
                CHECK (phone_e164 IS NOT NULL OR email IS NOT NULL)
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_suppression_entries_phone_e164
        ON suppression_entries(phone_e164)
        WHERE phone_e164 IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_suppression_entries_email
        ON suppression_entries(email)
        WHERE email IS NOT NULL;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_suppression_entries_phone ON suppression_entries(phone_e164);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_suppression_entries_email ON suppression_entries(email);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_suppression_entries_status ON suppression_entries(status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_suppression_entries_created_at ON suppression_entries(created_at);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_suppression_entries_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_suppression_entries_status;")
    op.execute("DROP INDEX IF EXISTS ix_suppression_entries_email;")
    op.execute("DROP INDEX IF EXISTS ix_suppression_entries_phone;")
    op.execute("DROP INDEX IF EXISTS uq_suppression_entries_email;")
    op.execute("DROP INDEX IF EXISTS uq_suppression_entries_phone_e164;")
    op.execute("DROP TABLE IF EXISTS suppression_entries;")

    op.execute("DROP INDEX IF EXISTS uq_return_requests_active_post_result;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_status;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_reason;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_buyer_id;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_lead_id;")
    op.execute("DROP INDEX IF EXISTS ix_return_requests_post_result_id;")
    op.execute("DROP TABLE IF EXISTS return_requests;")

    op.execute("DROP INDEX IF EXISTS uq_post_results_delivery_idempotency_key;")
    op.execute("ALTER TABLE post_results DROP COLUMN IF EXISTS delivery_idempotency_key;")
