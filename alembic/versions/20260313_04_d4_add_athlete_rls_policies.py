"""T5-08-B D4: enable athlete isolation via PostgreSQL row-level security.

Revision ID: 20260313_04
Revises: 20260313_03
Create Date: 2026-03-13
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260313_04"
down_revision = "20260313_03"
branch_labels = None
depends_on = None

_TABLES = (
    "daily_metrics",
    "training_log",
    "gear_usage",
    "personal_bests",
    "governance_outcomes",
    "model_calibration_metadata",
)
_POLICY_NAME = "titan_athlete_isolation"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    for table_name in _TABLES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {_POLICY_NAME} ON {table_name}")
        op.execute(
            f"""
            CREATE POLICY {_POLICY_NAME} ON {table_name}
            USING (athlete_id = current_setting('app.current_athlete_id', true))
            WITH CHECK (athlete_id = current_setting('app.current_athlete_id', true))
            """
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    for table_name in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {_POLICY_NAME} ON {table_name}")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
