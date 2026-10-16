"""Plan task 11 (D-012, D-028, D-037): CS performances are stored and read per athlete (v28)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
def test_fresh_database_has_the_column_and_new_rows_belong_to_the_owner(db) -> None:
    columns = {row[1]: row for row in db.conn.execute("PRAGMA table_info(cs_performances)")}
    assert columns["athlete_id"][3] == 1  # NOT NULL
    assert columns["athlete_id"][4] == "'owner'"
    db.log_cs_performance("2026-03-01", 3000, 700.0)
    assert db.conn.execute("SELECT athlete_id FROM cs_performances").fetchall() == [("owner",)]


@pytest.mark.unit
def test_v28_migration_gives_existing_rows_to_the_owner(tmp_path: Path) -> None:
    db_path = tmp_path / "v27.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE cs_performances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                distance_m REAL NOT NULL,
                time_sec REAL NOT NULL,
                surface TEXT DEFAULT 'ROAD',
                wind_adjusted INTEGER DEFAULT 0
            )
        """)
        conn.execute(
            "INSERT INTO cs_performances (date, distance_m, time_sec) VALUES ('2026-02-01', 5000, 1140.0)"
        )
        conn.execute("PRAGMA user_version = 27")
    conn.close()

    db = DatabaseManager(db_name=db_path.name, db_dir=tmp_path)
    try:
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 29
        assert db.conn.execute("SELECT athlete_id FROM cs_performances").fetchall() == [("owner",)]
        assert db.get_cs_performances() == [("2026-02-01", 5000.0, 1140.0)]
    finally:
        db.close()


@pytest.mark.unit
def test_v28_migration_is_idempotent(db) -> None:
    cursor = db.conn.cursor()
    db._apply_v28_migrations(cursor)
    db._apply_v28_migrations(cursor)
    names = [row[1] for row in db.conn.execute("PRAGMA table_info(cs_performances)")]
    assert names.count("athlete_id") == 1


@pytest.mark.unit
def test_writes_keep_the_athlete(db) -> None:
    db.log_cs_performance("2026-03-01", 3000, 700.0)
    db.log_cs_performance("2026-03-02", 5000, 1150.0, athlete_id="a1")
    rows = db.conn.execute("SELECT date, athlete_id FROM cs_performances ORDER BY date").fetchall()
    assert rows == [("2026-03-01", "owner"), ("2026-03-02", "a1")]
    assert db.get_cs_performances() == [("2026-03-01", 3000.0, 700.0)]


@pytest.mark.unit
def test_sqlite_adapter_forwards_the_athlete(db) -> None:
    from titan.core.persistence import SQLiteAdapter

    SQLiteAdapter(manager=db).log_cs_performance("2026-03-03", 3000, 695.0, athlete_id="a2")
    assert db.conn.execute("SELECT athlete_id FROM cs_performances").fetchall() == [("a2",)]


@pytest.mark.unit
def test_stage3_each_athlete_reads_only_its_own_cs_performances(db) -> None:
    db.log_cs_performance("2026-03-01", 3000, 700.0)
    db.log_cs_performance("2026-03-02", 5000, 1150.0, athlete_id="a1")
    db.log_cs_performance("2026-03-05", 3000, 690.0, athlete_id="a1")

    assert db.get_cs_performances() == [("2026-03-01", 3000.0, 700.0)]
    assert db.get_cs_performances(athlete_id="a1") == [
        ("2026-03-05", 3000.0, 690.0),
        ("2026-03-02", 5000.0, 1150.0),
    ]
    assert db.get_cs_performances(limit=1, athlete_id="a1") == [("2026-03-05", 3000.0, 690.0)]
    assert db.get_cs_performances(athlete_id="nobody") == []
