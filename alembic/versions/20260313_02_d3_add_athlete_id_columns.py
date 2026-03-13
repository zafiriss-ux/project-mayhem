"""T5-08-B D3: add athlete_id column to persistence tables.

Revision ID: 20260313_02
Revises: 20260313_01
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260313_02"
down_revision = "20260313_01"
branch_labels = None
depends_on = None

_TABLES = (
    "daily_metrics",
    "training_log",
    "gear_usage",
    "personal_bests",
    "governance_outcomes",
)


def upgrade() -> None:
    for table_name in _TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "athlete_id",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'default'"),
            ),
        )


def downgrade() -> None:
    for table_name in reversed(_TABLES):
        op.drop_column(table_name, "athlete_id")
