"""T5-13 tests for coach_audit_log migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command


def _make_config(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _table_exists(db_path: Path, table_name: str) -> bool:
    with sqlite3.connect(db_path) as connection:
        query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
        return connection.execute(query, (table_name,)).fetchone() is not None


def _column_metadata(db_path: Path, table_name: str) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(f"PRAGMA table_info({table_name})").fetchall()


@pytest.mark.integration
def test_t5_13_migration_upgrade_creates_coach_audit_log_with_expected_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "t5_13_upgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")

    assert _table_exists(db_path, "coach_audit_log")
    columns = {row[1]: row for row in _column_metadata(db_path, "coach_audit_log")}
    assert set(columns) == {
        "id",
        "coach_id",
        "athlete_id",
        "action_type",
        "resource",
        "action_detail",
        "performed_at",
    }
    assert columns["coach_id"][3] == 1
    assert columns["athlete_id"][3] == 1
    assert columns["action_type"][3] == 1
    assert columns["resource"][3] == 1
    assert columns["performed_at"][3] == 1


@pytest.mark.integration
def test_t5_13_migration_downgrade_removes_coach_audit_log(tmp_path: Path) -> None:
    db_path = tmp_path / "t5_13_downgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "20260316_01")

    assert not _table_exists(db_path, "coach_audit_log")
