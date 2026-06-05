"""Regression tests for CTL/ATL INSUFFICIENT DATA bug.

Root cause: save_session() omitted athlete_id from INSERT, so rows got the
schema DEFAULT ('default' after the v8 migration ran). get_training_load_history()
queries WHERE athlete_id='owner', finding nothing → CTL/ATL returned 0 /
TSBEngine reported "INSUFFICIENT DATA".

Fix: save_session() now accepts athlete_id="owner" and writes it explicitly;
_apply_v18_migrations() backfills existing rows where athlete_id='default'→'owner'.
"""

import sqlite3
from datetime import date, timedelta

import pytest

from titan.core.database import DatabaseManager


def _recent(days_ago: int = 1) -> str:
    """Return an ISO date string N days before today (stays within any lookback window)."""
    return (date.today() - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    db = DatabaseManager(db_path)
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Core fix: save_session stores training_load under athlete_id='owner'
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_save_session_trimp_stored_nonzero(tmp_db):
    """save_session with training_load=50 must appear in get_training_load_history."""
    tmp_db.save_session(
        date=_recent(1),
        session_type="EASY",
        distance_km=10.0,
        duration_sec=3600,
        avg_hr=135,
        max_hr=142,
        training_load=50,
    )
    history = tmp_db.get_training_load_history(60)
    assert len(history) >= 1, "Expected at least one row in training load history"
    loads = [load for _date, load in history]
    assert any(load > 0 for load in loads), (
        f"Expected a non-zero training_load in history, got: {loads}"
    )


@pytest.mark.integration
def test_save_session_athlete_id_defaults_to_owner(tmp_db):
    """Rows saved without explicit athlete_id must be stored as 'owner'."""
    target_date = _recent(2)
    tmp_db.save_session(
        date=target_date,
        session_type="TEMPO",
        distance_km=8.0,
        duration_sec=2400,
        training_load=70,
    )
    conn = sqlite3.connect(str(tmp_db.db_path))
    rows = conn.execute(
        "SELECT athlete_id FROM training_log WHERE date = ?", (target_date,)
    ).fetchall()
    conn.close()
    assert rows, f"No row found for date {target_date}"
    assert rows[0][0] == "owner", (
        f"Expected athlete_id='owner', got '{rows[0][0]}'"
    )


@pytest.mark.integration
def test_save_session_explicit_athlete_id(tmp_db):
    """Explicit athlete_id is written verbatim."""
    target_date = _recent(3)
    tmp_db.save_session(
        date=target_date,
        session_type="EASY",
        distance_km=5.0,
        duration_sec=1800,
        training_load=30,
        athlete_id="athlete_42",
    )
    conn = sqlite3.connect(str(tmp_db.db_path))
    rows = conn.execute(
        "SELECT athlete_id FROM training_log WHERE date = ?", (target_date,)
    ).fetchall()
    conn.close()
    assert rows and rows[0][0] == "athlete_42"


@pytest.mark.integration
def test_get_training_load_history_respects_athlete_id(tmp_db):
    """History is isolated per athlete_id — cross-athlete rows are invisible."""
    tmp_db.save_session(
        date=_recent(4), session_type="EASY", distance_km=10.0,
        duration_sec=3600, training_load=60, athlete_id="owner",
    )
    tmp_db.save_session(
        date=_recent(5), session_type="EASY", distance_km=8.0,
        duration_sec=2800, training_load=45, athlete_id="other",
    )
    history_owner = tmp_db.get_training_load_history(60, athlete_id="owner")
    history_other = tmp_db.get_training_load_history(60, athlete_id="other")

    owner_loads = [load for _, load in history_owner]

    assert any(load > 0 for load in owner_loads), "owner should see its session"
    assert len(history_owner) == 1, "owner should see exactly its own session"
    assert len(history_other) == 1, "other should see exactly its own session"


# ---------------------------------------------------------------------------
# v18 backfill migration (unit-level: call _apply_v18_migrations directly)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_v18_migration_backfills_default_athlete_id(tmp_db):
    """_apply_v18_migrations must UPDATE athlete_id='default'→'owner'.

    We insert a row with athlete_id='default' directly via SQL to simulate the
    legacy state left by the erroneous v8 migration, then call the backfill
    and verify the row is now visible to get_training_load_history().
    """
    row_date = _recent(5)
    conn = sqlite3.connect(str(tmp_db.db_path))
    conn.execute(
        "INSERT INTO training_log (athlete_id, date, session_type, distance_km, "
        "duration_sec, training_load) "
        "VALUES ('default', ?, 'EASY', 10.0, 3600, 80)",
        (row_date,),
    )
    conn.commit()

    # Confirm row is NOT visible before backfill
    history_before = tmp_db.get_training_load_history(60)
    dates_before = [d for d, _ in history_before]
    assert row_date not in dates_before, "Legacy 'default' row should be invisible before backfill"

    # Run the v18 backfill
    with tmp_db._lock:
        cursor = conn.cursor()
        tmp_db._apply_v18_migrations(cursor)
        conn.commit()
    conn.close()

    # Now the row must be visible
    history_after = tmp_db.get_training_load_history(60)
    loads_after = [load for _, load in history_after]
    assert any(load > 0 for load in loads_after), (
        f"Backfilled row should appear in history with nonzero load; got: {loads_after}"
    )


# ---------------------------------------------------------------------------
# Import script integration: compute_trimp_simple + save_session round-trip
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_import_csv_produces_nonzero_trimp(tmp_db):
    """import_garmin_csv helper functions produce nonzero TRIMP stored in DB.

    Exercises compute_trimp_simple and the save_session round-trip directly,
    matching the logic in scripts/import_garmin_csv.py main().
    """
    from scripts.import_garmin_csv import _synthetic_garmin_id, compute_trimp_simple

    athlete_max_hr = 180
    sessions = [
        (_recent(3), "EASY",     10.0, 3600, 140, athlete_max_hr),
        (_recent(5), "TEMPO",     8.0, 2400, 155, athlete_max_hr),
        (_recent(7), "LONG_RUN", 22.0, 7800, 138, athlete_max_hr),
    ]

    for date_str, session_type, dist, dur, avg_hr, max_hr in sessions:
        trimp = compute_trimp_simple(dur, avg_hr, max_hr)
        assert trimp > 0, f"compute_trimp_simple returned 0 for avg_hr={avg_hr}, max_hr={max_hr}"
        synthetic_id = _synthetic_garmin_id(date_str, dist, dur)
        tmp_db.save_session(
            date=date_str,
            session_type=session_type,
            distance_km=dist,
            duration_sec=dur,
            avg_hr=avg_hr,
            max_hr=max_hr,
            training_load=int(trimp),
            athlete_id="owner",
            garmin_activity_id=synthetic_id,
        )

    history = tmp_db.get_training_load_history(14)
    assert len(history) == 3, (
        f"Expected 3 imported sessions in history, got {len(history)}"
    )
    loads = [load for _, load in history]
    assert all(load > 0 for load in loads), (
        f"All imported rows should have nonzero training_load; got: {loads}"
    )


# ---------------------------------------------------------------------------
# NULL training_load regression — must not throw TypeError / must return data
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_training_load_history_returns_data(tmp_db):
    """get_training_load_history returns valid rows even when NULL rows exist.

    Root cause: float(None) raised TypeError when a legacy NULL training_load
    row was encountered, silently swallowed by DailyCoach._hydrate_engines,
    leaving daily_loads empty → TSBEngine reported INSUFFICIENT DATA.
    Fix: SQL filter adds AND training_load IS NOT NULL; Python loop guards None.
    """
    import sqlite3

    # Insert 10 valid rows via save_session
    for i in range(1, 11):
        tmp_db.save_session(
            date=_recent(i),
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            avg_hr=135,
            max_hr=150,
            training_load=55,
            athlete_id="owner",
        )
    # Insert a NULL training_load row directly (simulates legacy/Garmin-imported data)
    conn = sqlite3.connect(str(tmp_db.db_path))
    conn.execute(
        "INSERT INTO training_log "
        "(athlete_id, date, session_type, distance_km, duration_sec, training_load) "
        "VALUES ('owner', ?, 'EASY', 8.0, 3200, NULL)",
        (_recent(11),),
    )
    conn.commit()
    conn.close()

    result = tmp_db.get_training_load_history(60)
    assert len(result) == 10, (
        f"Expected 10 non-NULL rows, got {len(result)}"
    )
    assert all(r["load"] > 0 if isinstance(r, dict) else r[1] > 0 for r in result), (
        f"All returned rows must have load > 0; got: {result[:3]}"
    )


@pytest.mark.integration
def test_tsb_calculates_with_training_log_data(tmp_db):
    """TSBEngine produces a non-None CTL when training_log has valid rows.

    Verifies the full pipeline: save_session → get_training_load_history →
    TSBEngine.add_daily_load → calculate_ctl returns a float (not None / INSUFFICIENT DATA).
    """
    import sqlite3

    from titan.science.tsb_engine import TSBEngine

    # Insert 10 valid rows and one NULL row
    for i in range(1, 11):
        tmp_db.save_session(
            date=_recent(i),
            session_type="EASY",
            distance_km=12.0,
            duration_sec=4200,
            avg_hr=138,
            max_hr=155,
            training_load=60,
            athlete_id="owner",
        )
    conn = sqlite3.connect(str(tmp_db.db_path))
    conn.execute(
        "INSERT INTO training_log "
        "(athlete_id, date, session_type, distance_km, duration_sec, training_load) "
        "VALUES ('owner', ?, 'EASY', 5.0, 1800, NULL)",
        (_recent(12),),
    )
    conn.commit()
    conn.close()

    loads = tmp_db.get_training_load_history(60)
    assert len(loads) == 10, f"Expected 10 rows, got {len(loads)}"

    tsb = TSBEngine()
    for date_str, load in reversed(loads):
        tsb.add_daily_load(date_str, float(load))

    ctl = tsb.calculate_ctl()
    assert ctl is not None, "CTL must be a float, not None (INSUFFICIENT DATA)"
    assert ctl > 0, f"CTL must be > 0 with nonzero training loads; got {ctl}"


# ---------------------------------------------------------------------------
# training_load > 0 filter: zero-load rows excluded; historical rows included
# ---------------------------------------------------------------------------

def _date_str(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


@pytest.mark.integration
def test_get_training_load_history_returns_188(tmp_db):
    """get_training_load_history(400) returns all 188 rows with training_load > 0.

    Simulates the production scenario where 188 historical rows span
    Apr 2025-May 2026 (up to 400 days ago) with training_load=55 each.
    All must be returned and all loads must be > 0.
    """
    conn = sqlite3.connect(str(tmp_db.db_path))
    for i in range(1, 189):
        conn.execute(
            "INSERT INTO training_log "
            "(athlete_id, date, session_type, distance_km, duration_sec, training_load) "
            "VALUES ('owner', ?, 'EASY', 10.0, 3600, 55)",
            (_date_str(i),),
        )
    conn.commit()
    conn.close()

    result = tmp_db.get_training_load_history(400)
    assert len(result) == 188, (
        f"Expected 188 rows from 400-day window, got {len(result)}"
    )
    assert all(r[1] > 0 for r in result), (
        f"All returned rows must have training_load > 0; first 3: {result[:3]}"
    )


@pytest.mark.integration
def test_get_training_load_history_date_window(tmp_db):
    """Date window filter returns only rows within the requested window.

    Inserts 50 rows in the last 30 days and 50 rows older than 90 days.
    get_training_load_history(90) must return only the 50 recent rows.
    """
    conn = sqlite3.connect(str(tmp_db.db_path))
    # 50 rows in last 30 days (days 1..50 ago, all within 90-day window)
    for i in range(1, 51):
        conn.execute(
            "INSERT INTO training_log "
            "(athlete_id, date, session_type, distance_km, duration_sec, training_load) "
            "VALUES ('owner', ?, 'EASY', 10.0, 3600, 58)",
            (_date_str(i),),
        )
    # 50 rows older than 90 days (days 100..149 ago, outside 90-day window)
    for i in range(100, 150):
        conn.execute(
            "INSERT INTO training_log "
            "(athlete_id, date, session_type, distance_km, duration_sec, training_load) "
            "VALUES ('owner', ?, 'EASY', 10.0, 3600, 57)",
            (_date_str(i),),
        )
    conn.commit()
    conn.close()

    result = tmp_db.get_training_load_history(90)
    assert len(result) == 50, (
        f"Expected 50 rows within 90-day window, got {len(result)}"
    )
