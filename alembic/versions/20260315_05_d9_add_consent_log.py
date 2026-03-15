"""T5-08-B D9: add consent_log table.

Revision ID: 20260315_05
Revises: 20260313_04
Create Date: 2026-03-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260315_05"
down_revision = "20260313_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "athlete_id",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
        sa.Column("consent_type", sa.Text(), nullable=False),
        sa.Column("granted_at", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("consent_log")
