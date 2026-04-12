"""ADR-0052 Stage 1: add athlete_threshold_offsets table.

Revision ID: 20260412_01
Revises: 20260410_01
Create Date: 2026-04-12

Stage 1 of ADR-0052 (Population-Specific Threshold Adaptation via
OutcomeTracker).  Creates the per-athlete threshold offset table that
will be consumed by ThresholdAdapter in Stage 2.  No application logic
is wired in this migration — schema only.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260412_01"
down_revision = "20260410_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "athlete_threshold_offsets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("athlete_id", sa.Text(), nullable=False),
        sa.Column("threshold_key", sa.Text(), nullable=False),
        sa.Column("delta_value", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.UniqueConstraint("athlete_id", "threshold_key", name="uq_athlete_threshold"),
        sa.CheckConstraint("source IN ('manual', 'calibration')", name="ck_source_enum"),
        sa.CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_confidence_range"),
    )


def downgrade() -> None:
    op.drop_table("athlete_threshold_offsets")
