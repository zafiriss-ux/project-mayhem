"""T5-08-B D4 tests for PostgreSQL RLS migration behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

MIGRATION_PATH = Path("alembic/versions/20260313_04_d4_add_athlete_rls_policies.py")


class _FakeOp:
    def __init__(self, dialect_name: str) -> None:
        self._dialect_name = dialect_name
        self.executed: list[str] = []

    def get_bind(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=SimpleNamespace(name=self._dialect_name))

    def execute(self, sql: str) -> None:
        normalized = " ".join(sql.split())
        self.executed.append(normalized)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("t5_08b_d4_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_enables_rls_and_creates_policy_for_all_d4_tables() -> None:
    migration = _load_migration_module()
    fake_op = _FakeOp("postgresql")
    migration.op = fake_op

    migration.upgrade()

    expected_tables = [
        "daily_metrics",
        "training_log",
        "gear_usage",
        "personal_bests",
        "governance_outcomes",
        "model_calibration_metadata",
    ]
    for table_name in expected_tables:
        assert f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY" in fake_op.executed
        assert f"DROP POLICY IF EXISTS titan_athlete_isolation ON {table_name}" in fake_op.executed
        create_policy_sql = (
            f"CREATE POLICY titan_athlete_isolation ON {table_name} "
            "USING (athlete_id = current_setting('app.current_athlete_id', true)) "
            "WITH CHECK (athlete_id = current_setting('app.current_athlete_id', true))"
        )
        assert create_policy_sql in fake_op.executed



def test_downgrade_drops_policy_and_disables_rls_for_all_d4_tables() -> None:
    migration = _load_migration_module()
    fake_op = _FakeOp("postgresql")
    migration.op = fake_op

    migration.downgrade()

    expected_tables = [
        "model_calibration_metadata",
        "governance_outcomes",
        "personal_bests",
        "gear_usage",
        "training_log",
        "daily_metrics",
    ]
    for table_name in expected_tables:
        assert f"DROP POLICY IF EXISTS titan_athlete_isolation ON {table_name}" in fake_op.executed
        assert f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY" in fake_op.executed

def test_upgrade_and_downgrade_are_noop_for_sqlite_path() -> None:
    migration = _load_migration_module()
    fake_op = _FakeOp("sqlite")
    migration.op = fake_op

    migration.upgrade()
    migration.downgrade()

    assert fake_op.executed == []
