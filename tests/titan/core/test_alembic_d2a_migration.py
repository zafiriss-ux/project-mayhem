"""T5-08-B D2a tests for Alembic wiring + five-table migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

_EXPECTED_TABLES = {
    "daily_metrics",
    "training_log",
    "gear_usage",
    "personal_bests",
    "governance_outcomes",
}


def _make_config(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {name for (name,) in rows}


@pytest.mark.integration
def test_d2a_upgrade_creates_expected_five_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "d2a_upgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")

    table_names = _table_names(db_path)
    assert _EXPECTED_TABLES.issubset(table_names)


@pytest.mark.integration
def test_d2a_round_trip_downgrade_then_upgrade_is_clean(tmp_path: Path) -> None:
    db_path = tmp_path / "d2a_roundtrip.db"
    config = _make_config(db_path)

    command.upgrade(config, revision="20260313_01")
    command.downgrade(config, "-1")

    downgraded_tables = _table_names(db_path)
    assert _EXPECTED_TABLES.isdisjoint(downgraded_tables)

    command.upgrade(config, "head")
    reupgraded_tables = _table_names(db_path)
    assert _EXPECTED_TABLES.issubset(reupgraded_tables)
