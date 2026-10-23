"""D-077, schema v29: training_log has an (athlete_id, date) index.

The SQLite assessment found every athlete-scoped date-window read of training_log
doing a full table scan. The index is additive (AGENTS §13.3).
"""

from __future__ import annotations

import sqlite3

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager

INDEX = "idx_training_log_athlete_date"


def _index_columns(conn) -> list[str]:
    return [row[2] for row in conn.execute(f"PRAGMA index_info({INDEX})").fetchall()]


@pytest.mark.unit
def test_a_new_database_has_the_index(tmp_path) -> None:
    db = DatabaseManager(db_dir=tmp_path)
    try:
        assert _index_columns(db.conn) == ["athlete_id", "date"]
        assert SCHEMA_VERSION == 34
    finally:
        db.close()


@pytest.mark.unit
def test_a_v28_database_gets_the_index_on_open(tmp_path) -> None:
    db = DatabaseManager(db_dir=tmp_path)
    db.conn.execute(f"DROP INDEX {INDEX}")
    db.conn.execute("PRAGMA user_version = 28")
    db.conn.commit()
    db.close()

    raw = sqlite3.connect(tmp_path / "titan_core.db")
    assert _index_columns(raw) == []
    raw.close()

    db = DatabaseManager(db_dir=tmp_path)
    try:
        assert _index_columns(db.conn) == ["athlete_id", "date"]
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == 34
    finally:
        db.close()


@pytest.mark.unit
def test_the_load_history_read_searches_the_index(tmp_path) -> None:
    db = DatabaseManager(db_dir=tmp_path)
    try:
        plan = " ".join(
            row[3] for row in db.conn.execute(
                "EXPLAIN QUERY PLAN SELECT date, training_load FROM training_log "
                "WHERE athlete_id = ? AND date >= ?", ("owner", "2026-01-01"),
            ).fetchall()
        )
        assert f"SEARCH training_log USING INDEX {INDEX}" in plan
    finally:
        db.close()
