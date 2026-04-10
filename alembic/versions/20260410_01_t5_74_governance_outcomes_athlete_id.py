"""T5-74: add athlete_id column to governance_outcomes.

Revision ID: 20260410_01
Revises: 20260316_02
Create Date: 2026-04-10

Prerequisite for ADR-0033 Layer 3 (multi-athlete coaching pipeline).
Uses IF NOT EXISTS to remain safe if migration 20260313_02 already
added the column via the batch athlete_id sweep (T5-08-B D3).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260410_01"
down_revision = "20260316_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE governance_outcomes "
        "ADD COLUMN IF NOT EXISTS athlete_id TEXT NOT NULL DEFAULT 'default'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE governance_outcomes DROP COLUMN IF EXISTS athlete_id")
