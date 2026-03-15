"""T5-08-B D9 tests for consent_log migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def _make_config(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _column_metadata(db_path: Path, table_name: str) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(f"PRAGMA table_info({table_name})").fetchall()


def _table_exists(db_path: Path, table_name: str) -> bool:
    with sqlite3.connect(db_path) as connection:
        query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
        return connection.execute(query, (table_name,)).fetchone() is not None


def test_d9_upgrade_creates_consent_log_with_expected_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "d9_upgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")

    assert _table_exists(db_path, "consent_log")

    columns = {row[1]: row for row in _column_metadata(db_path, "consent_log")}
    assert set(columns) == {
        "id",
        "athlete_id",
        "consent_type",
        "granted_at",
        "revoked_at",
    }
    assert columns["athlete_id"][3] == 1
    assert columns["athlete_id"][4] == "'default'"
    assert columns["consent_type"][3] == 1
    assert columns["granted_at"][3] == 1
    assert columns["revoked_at"][3] == 0

    pk_columns = [row[1] for row in _column_metadata(db_path, "consent_log") if row[5] > 0]
    assert pk_columns == ["id"]


def test_d9_downgrade_removes_consent_log_table(tmp_path: Path) -> None:
    db_path = tmp_path / "d9_downgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "20260313_04")

    assert not _table_exists(db_path, "consent_log")
