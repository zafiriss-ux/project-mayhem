"""T5-74: add athlete_id column to governance_outcomes.

Revision ID: 20260410_01
Revises: 20260316_02
Create Date: 2026-04-10

Prerequisite for ADR-0033 Layer 3 (multi-athlete coaching pipeline).
Uses dialect-aware inspection to remain safe if migration 20260313_02
already added the column via the batch athlete_id sweep (T5-08-B D3).
SQLite does not support IF NOT EXISTS in ALTER TABLE; use sa_inspect instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect  # noqa: PLC0415

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260410_01"
down_revision = "20260316_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = [c["name"] for c in sa_inspect(bind).get_columns("governance_outcomes")]
    if "athlete_id" not in cols:
        op.add_column(
            "governance_outcomes",
            sa.Column(
                "athlete_id",
                sa.Text(),
                nullable=False,
                server_default="default",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    gov_cols = [c["name"] for c in sa_inspect(bind).get_columns("governance_outcomes")]
    if "athlete_id" not in gov_cols:
        return  # column absent — nothing to remove

    # D3 migration (20260313_02) also added athlete_id to governance_outcomes as
    # part of the batch athlete_id sweep.  If D3 is still applied, daily_metrics
    # will also have athlete_id — in that case T5-74 downgrade is a no-op and D3
    # is responsible for removing the column when it is eventually downgraded.
    daily_cols = [c["name"] for c in sa_inspect(bind).get_columns("daily_metrics")]
    if "athlete_id" in daily_cols:
        return  # D3 still applied — column ownership belongs to D3, not T5-74

    op.drop_column("governance_outcomes", "athlete_id")
