"""T5-08-B D5: add model_calibration_metadata table.

Revision ID: 20260313_03
Revises: 20260313_02
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260313_03"
down_revision = "20260313_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_calibration_metadata",
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column(
            "athlete_id",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
        sa.Column("calibrated_at", sa.Text(), nullable=False),
        sa.Column(
            "calibrated_for",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
        sa.Column("baseline_hrv_ms", sa.Float(), nullable=True),
        sa.Column("baseline_vo2", sa.Float(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("model_name", "athlete_id", name="pk_model_calibration_metadata"),
    )


def downgrade() -> None:
    op.drop_table("model_calibration_metadata")
