"""T5-13: add coach_audit_log table.

Revision ID: 20260316_02
Revises: 20260316_01
Create Date: 2026-03-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260316_02"
down_revision = "20260316_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coach_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Text(), nullable=False),
        sa.Column("athlete_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("action_detail", sa.JSON(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("coach_audit_log")
