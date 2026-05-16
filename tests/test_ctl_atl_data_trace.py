"""Regression tests for CTL/ATL/TSB INSUFFICIENT DATA bug (data-trace suite).

Traces two failure scenarios that could cause TSBEngine to report INSUFFICIENT DATA
despite valid training_load rows existing in the database:

  1. Sparse data (2-3 day gaps, like CSV import) — TSBEngine must still produce CTL/ATL.
  2. Empty engine + rows inserted post-init — the hydration pipeline must re-read the DB
     and produce a non-None TSB (engine must not cache an empty state from init time).

Root cause (now fixed):
  database.py:get_training_load_history() raised TypeError on NULL training_load rows
  (float(None)), which was silently caught by DailyCoach._hydrate_engines_from_db(),
  leaving TSBEngine.daily_loads empty → calculate_tsb() returned (None, "INSUFFICIENT DATA")
  despite 188 valid rows in the DB.

Fix applied in commit 03017cf:
  - SQL query adds AND training_load IS NOT NULL
  - Python loop adds an explicit None guard as a second defence layer
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from titan.core.database import DatabaseManager
from titan.science.tsb_engine import TSBEngine  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recent(days_ago: int) -> str:
    """Return an ISO date string N days before today."""
    return (date.today() - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def tmp_db(tmp_path):
    db = DatabaseManager(str(tmp_path / "test.db"))
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Test 1: sparse data (2-3 day gaps) must still produce a non-None CTL
# ---------------------------------------------------------------------------


def test_tsb_sparse_data_produces_partial_ctl(tmp_db):
    """30 rows with 2-3 day gaps (like CSV import) must yield non-None CTL/ATL.

    Verifies that TSBEngine.calculate_ctl() / calculate_atl() do NOT require
    consecutive daily entries to return a value — any non-empty daily_loads list
    is sufficient for EMA computation.

    Failure mode caught: if the engine imposed a minimum consecutive-day requirement
    (e.g. 42 consecutive days), sparse imports would permanently return INSUFFICIENT
    DATA even though many months of valid training history exist.
    """
    # Build 30 rows with a realistic 2-3 day gap pattern (Mon / Wed / Fri / Sat)
    # covering ~10 weeks so dates stay within a 90-day lookback window.
    training_days: list[tuple[str, int]] = []
    today = date.today()
    gap_pattern = [2, 2, 1, 3]  # gaps after Mon, Wed, Fri, Sat
    current = today - timedelta(days=90)  # start 90 days ago
    gap_idx = 0
    while len(training_days) < 30:
        training_days.append((current.isoformat(), 56 + (len(training_days) % 5)))
        current = current + timedelta(days=gap_pattern[gap_idx % len(gap_pattern)])
        gap_idx += 1

    # Insert via save_session so athlete_id='owner' is written correctly
    for date_str, load in training_days:
        tmp_db.save_session(
            date=date_str,
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            training_load=load,
            athlete_id="owner",
        )

    # Fetch history (lookback long enough to capture all inserted rows)
    loads = tmp_db.get_training_load_history(days=120)
    assert len(loads) >= 1, (
        "Expected at least one row in training load history; got none. "
        "Sparse rows must survive the date-window filter."
    )

    # Feed into TSBEngine oldest-first (mirrors DailyCoach._hydrate_engines_from_db)
    tsb = TSBEngine()
    for date_str, load in reversed(loads):
        tsb.add_daily_load(date_str, float(load))

    ctl = tsb.calculate_ctl()
    atl = tsb.calculate_atl()
    tsb_value, status = tsb.calculate_tsb()

    assert ctl is not None, (
        f"CTL must be non-None with {len(loads)} sparse rows; got None (INSUFFICIENT DATA). "
        "Sparse 2-3 day gaps must not block EMA computation."
    )
    assert atl is not None, (
        f"ATL must be non-None with {len(loads)} sparse rows; got None."
    )
    assert tsb_value is not None, (
        f"TSB must be non-None; got status='{status}' (expected non-INSUFFICIENT DATA)."
    )
    assert status != "INSUFFICIENT DATA", (
        f"TSBEngine must not report INSUFFICIENT DATA with {len(loads)} valid loads; "
        f"got status='{status}'."
    )
    assert ctl > 0.0, f"CTL must be positive with positive training loads; got {ctl}"
    assert atl > 0.0, f"ATL must be positive with positive training loads; got {atl}"


# ---------------------------------------------------------------------------
# Test 2: engine initialised with empty DB, rows inserted afterward — hydration
#         pipeline must re-read DB and return non-None TSB
# ---------------------------------------------------------------------------


def test_tsb_engine_rereads_db_on_calculate(tmp_db):
    """TSBEngine initialised empty then hydrated from DB rows must return non-None TSB.

    Simulates the production scenario:
      1. TSBEngine is created (empty daily_loads) at DailyCoach init time.
      2. Rows are inserted into the DB AFTER the engine is created
         (e.g. via CSV import or Garmin sync that completes after startup).
      3. _hydrate_engines_from_db() is called → reads DB via get_training_load_history()
         → loads rows into TSBEngine.daily_loads via add_daily_load().
      4. calculate_tsb() is called → must return a non-None value.

    Failure mode caught: if the engine cached an empty state from init time and
    never re-polled the DB, calculate_tsb() would always return INSUFFICIENT DATA
    regardless of how many rows were imported after startup.

    The fix (NULL training_load guard in get_training_load_history) ensures that
    rows with NULL training_load do not raise TypeError, preventing the exception
    from silently emptying daily_loads in _hydrate_engines_from_db.
    """
    # Step 1: engine created with empty DB (daily_loads is empty at this point)
    tsb = TSBEngine()
    assert tsb.daily_loads == [], "Pre-condition: engine must start empty"

    # Step 2: insert rows into DB (simulates import happening after startup)
    for i in range(1, 16):
        tmp_db.save_session(
            date=_recent(i * 2),        # every other day → realistic sparse data
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            avg_hr=138,
            max_hr=155,
            training_load=58,           # non-null, non-zero (like the production 56-60 range)
            athlete_id="owner",
        )

    # Also insert one NULL training_load row to confirm the NULL guard holds
    conn = sqlite3.connect(str(tmp_db.db_path))
    conn.execute(
        "INSERT INTO training_log "
        "(athlete_id, date, session_type, distance_km, duration_sec, training_load) "
        "VALUES ('owner', ?, 'EASY', 5.0, 1800, NULL)",
        (_recent(60),),
    )
    conn.commit()
    conn.close()

    # Step 3: simulate _hydrate_engines_from_db() — re-read DB into engine
    loads = tmp_db.get_training_load_history(days=60)
    assert len(loads) == 15, (
        f"Expected 15 non-NULL rows from DB; got {len(loads)}. "
        "The NULL guard must exclude the NULL row inserted directly via SQL."
    )

    tsb.daily_loads.clear()
    for date_str, load in reversed(loads):   # oldest-first for correct EMA
        tsb.add_daily_load(date_str, float(load))

    # Step 4: calculate_tsb() must now return a non-None value
    tsb_value, status = tsb.calculate_tsb()

    assert tsb_value is not None, (
        "TSBEngine must return a non-None TSB after hydration from DB. "
        f"Got status='{status}' (INSUFFICIENT DATA). "
        "Engine must not use a stale empty state from init time — "
        "re-hydration via add_daily_load must be effective."
    )
    assert status != "INSUFFICIENT DATA", (
        f"Expected a valid TSB status after DB hydration; got '{status}'."
    )

    ctl = tsb.calculate_ctl()
    atl = tsb.calculate_atl()
    assert ctl is not None and ctl > 0.0, f"CTL must be positive after hydration; got {ctl}"
    assert atl is not None and atl > 0.0, f"ATL must be positive after hydration; got {atl}"
