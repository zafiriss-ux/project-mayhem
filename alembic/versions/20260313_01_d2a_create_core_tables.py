"""T5-08-B D2a: create current persistence tables.

Revision ID: 20260313_01
Revises:
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260313_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("hrv_rmssd", sa.Float(), nullable=True),
        sa.Column("resting_hr", sa.Integer(), nullable=True),
        sa.Column("sleep_hours", sa.Float(), nullable=True),
        sa.Column("sleep_quality", sa.Integer(), nullable=True),
        sa.Column("soreness", sa.Integer(), nullable=True),
        sa.Column("fatigue_level", sa.Integer(), nullable=True),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("date", name="uq_daily_metrics_date"),
    )

    op.create_table(
        "gear_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shoe_name", sa.Text(), nullable=False),
        sa.Column("total_km", sa.Float(), nullable=True, server_default=sa.text("0")),
        sa.Column("last_used", sa.Text(), nullable=True),
        sa.Column(
            "compression_recovery_hours",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("24"),
        ),
        sa.Column("status", sa.Text(), nullable=True, server_default=sa.text("'ACTIVE'")),
        sa.Column("shoe_type", sa.Text(), nullable=True),
        sa.Column("max_km_limit", sa.Float(), nullable=True, server_default=sa.text("800")),
    )

    op.create_table(
        "training_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column("session_type", sa.Text(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("avg_hr", sa.Integer(), nullable=True),
        sa.Column("max_hr", sa.Integer(), nullable=True),
        sa.Column("rpe", sa.Integer(), nullable=True),
        sa.Column("training_load", sa.Integer(), nullable=True),
        sa.Column("shoe_id", sa.BigInteger(), nullable=True),
        sa.Column("surface", sa.Text(), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("zone_distribution", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["shoe_id"], ["gear_usage.id"], name="fk_training_log_shoe_id"),
    )

    op.create_table(
        "personal_bests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("time_sec", sa.Integer(), nullable=False),
        sa.Column("pace_sec_per_km", sa.Float(), nullable=True),
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column("race_name", sa.Text(), nullable=True),
    )

    op.create_table(
        "governance_outcomes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column("session_planned", sa.Text(), nullable=False),
        sa.Column("session_post_governance", sa.Text(), nullable=False),
        sa.Column("locks_applied_json", sa.Text(), nullable=False),
        sa.Column("governance_clean", sa.Integer(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("vlg_color", sa.Text(), nullable=False),
        sa.Column("apl_priority_vector_json", sa.Text(), nullable=False),
        sa.Column("lock_thresholds_active_json", sa.Text(), nullable=False),
        sa.Column("acwr", sa.Float(), nullable=False),
        sa.Column("tsb_value", sa.Float(), nullable=False),
        sa.Column("readiness_score", sa.Float(), nullable=False),
        sa.Column("glycogen_debt", sa.Float(), nullable=False),
        sa.Column("afi_value", sa.Float(), nullable=True),
        sa.Column("outcome_rpe", sa.Integer(), nullable=True),
        sa.Column("outcome_completed", sa.Integer(), nullable=True),
        sa.Column("outcome_session_type_actual", sa.Text(), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column(
            "decision_was_followed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "override_outcome_exclusion",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "outcome_independence_ok",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("algorithm_version_snapshot", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("governance_outcomes")
    op.drop_table("personal_bests")
    op.drop_table("training_log")
    op.drop_table("gear_usage")
    op.drop_table("daily_metrics")
