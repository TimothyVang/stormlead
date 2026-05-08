"""add skill proposal review table

Revision ID: 0007_skill_proposals
Revises: 0006_v1_paid_pilot_controls
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op

revision = "0007_skill_proposals"
down_revision = "0006_v1_paid_pilot_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_proposals (
            id uuid PRIMARY KEY,
            proposal_date date NOT NULL,
            proposal_type varchar(32) NOT NULL,
            skill_name varchar(128),
            title varchar(255) NOT NULL,
            rationale text,
            proposal_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            status varchar(32) NOT NULL DEFAULT 'pending_review',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_skill_proposals_type
                CHECK (proposal_type IN ('prompt_update', 'new_skill', 'retire_skill')),
            CONSTRAINT ck_skill_proposals_status
                CHECK (status IN ('pending_review', 'approved', 'rejected', 'applied'))
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_skill_proposals_proposal_date ON skill_proposals(proposal_date);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_skill_proposals_proposal_type ON skill_proposals(proposal_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_skill_proposals_skill_name ON skill_proposals(skill_name);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_skill_proposals_status ON skill_proposals(status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_skill_proposals_created_at ON skill_proposals(created_at);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_skill_proposals_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_skill_proposals_status;")
    op.execute("DROP INDEX IF EXISTS ix_skill_proposals_skill_name;")
    op.execute("DROP INDEX IF EXISTS ix_skill_proposals_proposal_type;")
    op.execute("DROP INDEX IF EXISTS ix_skill_proposals_proposal_date;")
    op.execute("DROP TABLE IF EXISTS skill_proposals;")
