"""T5-07-L3-A + T5-74: athletes canonical table + governance_outcomes owner backfill
+ drop model_calibration_metadata.calibrated_for.

Revision ID: 20260414_01
Revises: 20260412_01
Create Date: 2026-04-14

Implements the final schema obligations for:
  - T5-07-L3-A: athletes canonical table (ADR-0033 Layer 3 Phase 9 entry gate)
  - T5-74: governance_outcomes.athlete_id owner backfill + explicit INSERT path
  - SCHEMA_VERSION bump 12 → 13

Changes:
  1. CREATE TABLE athletes (owner seed row inserted).
  2. Backfill governance_outcomes.athlete_id: 'default'/'DEFAULT' → 'owner'.
  3. Drop redundant calibrated_for column from model_calibration_metadata
     (athlete_id already serves as the athlete FK in that table).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect  # noqa: PLC0415

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260414_01"
down_revision = "20260412_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. athletes canonical table ──────────────────────────────────────────
    op.create_table(
        "athletes",
        sa.Column("athlete_id", sa.Text(), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column(
            "is_cold_start",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("cold_start_ends_at", sa.Text()),
        sa.Column(
            "cold_start_sessions_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Seed owner row — dialect-aware for SQLite (datetime) vs PostgreSQL (now()).
    bind = op.get_bind()
    dialect = bind.dialect.name
    now_expr = "datetime('now')" if dialect == "sqlite" else "now()"

    op.execute(
        f"""
        INSERT INTO athletes
            (athlete_id, display_name, created_at, is_cold_start,
             cold_start_ends_at, cold_start_sessions_count)
        VALUES
            ('owner', 'Owner', {now_expr}, 0, {now_expr}, 30)
        ON CONFLICT DO NOTHING
        """  # noqa: S608
    )

    # ── 2. Backfill governance_outcomes.athlete_id ───────────────────────────
    op.execute(
        """
        UPDATE governance_outcomes
           SET athlete_id = 'owner'
         WHERE athlete_id IN ('default', 'DEFAULT')
        """  # noqa: S608
    )

    # ── 3. Drop calibrated_for from model_calibration_metadata ───────────────
    bind = op.get_bind()
    cols = [
        c["name"]
        for c in sa_inspect(bind).get_columns("model_calibration_metadata")
    ]
    if "calibrated_for" in cols:
        with op.batch_alter_table("model_calibration_metadata") as batch_op:
            batch_op.drop_column("calibrated_for")


def downgrade() -> None:
    # ── 3 reverse: restore calibrated_for ────────────────────────────────────
    bind = op.get_bind()
    cols = [
        c["name"]
        for c in sa_inspect(bind).get_columns("model_calibration_metadata")
    ]
    if "calibrated_for" not in cols:
        with op.batch_alter_table("model_calibration_metadata") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "calibrated_for",
                    sa.Text(),
                    nullable=False,
                    server_default="default",
                )
            )

    # ── 2 reverse: backfill is not reversed (data loss is acceptable for
    #   governance_outcomes.athlete_id since 'default' was a placeholder, not
    #   meaningful data; downgrade restores schema only).

    # ── 1 reverse: drop athletes table ───────────────────────────────────────
    op.drop_table("athletes")
