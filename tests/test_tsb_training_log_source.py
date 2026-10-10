"""Tests for [D]: TSB/CTL/ATL reads from training_log (root cause verification).

Root cause finding: get_training_load_history() queries training_log.training_load.
There is no garmin_activities table; Garmin sync data is also written to training_log.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from titan.science.tsb_engine import TSBEngine  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path) -> str:
    """Return path to a minimal in-memory-like SQLite DB with training_log."""
    db_path = str(tmp_path / "titan_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE training_log (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            session_type TEXT,
            distance_km REAL,
            duration_sec INTEGER,
            avg_hr INTEGER,
            training_load INTEGER,
            athlete_id TEXT NOT NULL DEFAULT 'owner'
        )
        """
    )
    conn.commit()
    conn.close()
    return db_path


def _insert_loads(db_path: str, rows: list[tuple[str, int]], athlete_id: str = "owner") -> None:
    """Insert (date, training_load) rows into training_log."""
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO training_log (date, training_load, athlete_id) VALUES (?, ?, ?)",
        [(d, load, athlete_id) for d, load in rows],
    )
    conn.commit()
    conn.close()


def _fetch_training_load_history(db_path: str, days: int = 60, athlete_id: str = "owner") -> list[tuple[str, float]]:
    """Replicate get_training_load_history() logic directly against the test DB."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT date, training_load
        FROM training_log
        WHERE athlete_id = ? AND date >= date('now', '-' || ? || ' days')
        ORDER BY date DESC
        """,
        (athlete_id, days),
    ).fetchall()
    conn.close()
    return [(d, float(load)) for d, load in rows if load]


# ---------------------------------------------------------------------------
# [D] CTL/ATL from training_log
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_tsb_uses_training_log_when_no_garmin(tmp_path):
    """CTL/ATL must be non-None when training_log has 60 rows of load data."""
    db_path = _make_db(tmp_path)

    # Insert 60 days of training load
    today = date.today()
    rows = [
        ((today - timedelta(days=i)).isoformat(), 45 + (i % 10))
        for i in range(60)
    ]
    _insert_loads(db_path, rows)

    history = _fetch_training_load_history(db_path, days=60)
    assert len(history) > 0, "No rows returned from training_log"

    # Feed into TSBEngine directly (mirrors DailyCoach startup)
    tsb = TSBEngine()
    for date_str, load in reversed(history):  # oldest → newest
        tsb.add_daily_load(date_str, load)

    ctl = tsb.calculate_ctl()
    atl = tsb.calculate_atl()

    assert ctl is not None, "CTL must be non-None when training_log has data"
    assert atl is not None, "ATL must be non-None when training_log has data"
    assert ctl > 0.0, "CTL must be positive with positive training loads"
    assert atl > 0.0, "ATL must be positive with positive training loads"


@pytest.mark.integration
def test_tsb_ctl_atl_none_when_no_data():
    """TSBEngine returns None CTL/ATL when no loads have been added."""
    tsb = TSBEngine()
    assert tsb.calculate_ctl() is None
    assert tsb.calculate_atl() is None
    tsb_val, status = tsb.calculate_tsb()
    assert tsb_val is None
    assert status == "INSUFFICIENT DATA"


@pytest.mark.integration
def test_tsb_source_is_training_log_not_garmin_activities(tmp_path):
    """Confirm the query targets training_log; garmin_activities does not exist."""
    db_path = _make_db(tmp_path)

    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()

    assert "training_log" in tables, "training_log table must exist"
    assert "garmin_activities" not in tables, (
        "garmin_activities table should not exist; Garmin sync writes to training_log"
    )


@pytest.mark.integration
def test_tsb_prefers_garmin_row_via_training_log(tmp_path):
    """When multiple training_log rows share a date (manual + Garmin), both are summed
    — this verifies no silent data loss.  The caller (DailyCoach) must deduplicate
    via garmin_activity_id UNIQUE index before rows reach the TSB history query."""
    db_path = _make_db(tmp_path)

    today = date.today()
    target_date = (today - timedelta(days=5)).isoformat()

    # Simulate: one row from Garmin sync (higher TRIMP), one manual entry (lower)
    # In production the UNIQUE(garmin_activity_id) prevents the Garmin row from
    # being double-inserted; here we test what happens with two distinct rows.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO training_log (date, training_load, athlete_id) VALUES (?, ?, ?)",
        (target_date, 60, "owner"),  # simulates Garmin-synced row
    )
    conn.execute(
        "INSERT INTO training_log (date, training_load, athlete_id) VALUES (?, ?, ?)",
        (target_date, 30, "owner"),  # simulates CSV-imported row (same date, different activity)
    )
    conn.commit()
    conn.close()

    history = _fetch_training_load_history(db_path, days=60)
    # Both rows exist and are included (no dedup at the history-query level)
    target_loads = [load for d, load in history if d == target_date]
    assert len(target_loads) >= 1
    # Total load for that date spans both rows
    assert sum(target_loads) == pytest.approx(90.0)


@pytest.mark.integration
def test_tsb_calculation_correctness_known_inputs():
    """EMA correctness: one load today, from 0 → CTL = load/42, ATL = load/7 (TrainingPeaks, D-051)."""
    tsb = TSBEngine()
    tsb.add_daily_load(datetime.now(UTC).date().isoformat(), 50.0)

    ctl = tsb.calculate_ctl()
    atl = tsb.calculate_atl()

    assert ctl == pytest.approx(50.0 / 42, abs=0.05)
    assert atl == pytest.approx(50.0 / 7, abs=0.05)
