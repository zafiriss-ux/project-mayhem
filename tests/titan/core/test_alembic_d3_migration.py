"""T5-08-B D3 tests for athlete_id schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command

_TABLES = (
    "daily_metrics",
    "training_log",
    "gear_usage",
    "personal_bests",
    "governance_outcomes",
)


def _make_config(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _column_metadata(db_path: Path, table_name: str) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(f"PRAGMA table_info({table_name})").fetchall()


def _athlete_column_row(db_path: Path, table_name: str) -> tuple | None:
    rows = _column_metadata(db_path, table_name)
    for row in rows:
        if row[1] == "athlete_id":
            return row
    return None


def test_d3_upgrade_adds_athlete_id_column_to_all_five_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "d3_upgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")

    for table_name in _TABLES:
        athlete_column = _athlete_column_row(db_path, table_name)
        assert athlete_column is not None
        assert athlete_column[3] == 1
        assert athlete_column[4] == "'default'"


def test_d3_downgrade_removes_athlete_id_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "d3_downgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "20260313_01")

    for table_name in _TABLES:
        assert _athlete_column_row(db_path, table_name) is None
