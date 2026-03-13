"""T5-08-B D5 tests for model_calibration_metadata migration."""

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


def test_d5_upgrade_creates_model_calibration_metadata_with_expected_contract(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "d5_upgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")

    assert _table_exists(db_path, "model_calibration_metadata")

    columns = {row[1]: row for row in _column_metadata(db_path, "model_calibration_metadata")}
    assert set(columns) == {
        "model_name",
        "athlete_id",
        "calibrated_at",
        "calibrated_for",
        "baseline_hrv_ms",
        "baseline_vo2",
        "schema_version",
    }
    assert columns["athlete_id"][3] == 1
    assert columns["athlete_id"][4] == "'default'"
    assert columns["calibrated_for"][4] == "'default'"

    pk_columns = [row[1] for row in _column_metadata(db_path, "model_calibration_metadata") if row[5] > 0]
    assert pk_columns == ["model_name", "athlete_id"]


def test_d5_downgrade_removes_model_calibration_metadata_table(tmp_path: Path) -> None:
    db_path = tmp_path / "d5_downgrade.db"
    config = _make_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "20260313_02")

    assert not _table_exists(db_path, "model_calibration_metadata")
