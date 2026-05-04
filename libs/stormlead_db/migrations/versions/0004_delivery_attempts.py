"""add delivery attempts table for idempotent post retries

Revision ID: 0004_delivery_attempts
Revises: 0003_paid_pilot_fields
Create Date: 2026-05-04

"""

from __future__ import annotations

from alembic import op

revision = "0004_delivery_attempts"
down_revision = "0003_paid_pilot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS delivery_attempts (
            id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES leads(id),
            buyer_id uuid NOT NULL REFERENCES buyers(id),
            post_attempt integer NOT NULL,
            idempotency_key varchar(64) NOT NULL,
            status varchar(32) NOT NULL,
            response_code integer,
            response_body_hash varchar(64),
            retry_count integer NOT NULL DEFAULT 0,
            next_retry_at timestamptz,
            error text,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_attempt_triplet ON delivery_attempts(lead_id, buyer_id, post_attempt);"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_attempt_idempotency_key ON delivery_attempts(idempotency_key);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_delivery_attempts_status ON delivery_attempts(status);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_delivery_attempts_created_at ON delivery_attempts(created_at);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_delivery_attempts_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_delivery_attempts_status;")
    op.execute("DROP INDEX IF EXISTS uq_delivery_attempt_idempotency_key;")
    op.execute("DROP INDEX IF EXISTS uq_delivery_attempt_triplet;")
    op.execute("DROP TABLE IF EXISTS delivery_attempts;")
