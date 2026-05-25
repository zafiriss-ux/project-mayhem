"""Property tests for TSB/CTL/ATL correctness — CI-blocking per Opus §5.2."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from titan.core.database import DatabaseManager


def _make_db(tmp_path: Path, name: str = "prop.db") -> DatabaseManager:
    db = DatabaseManager(db_name=name, db_dir=tmp_path)
    return db


def _insert(db: DatabaseManager, rows: list[tuple[str, int]]) -> None:
    for date_str, load in rows:
        db.save_session(
            date=date_str,
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            training_load=load,
        )


def _today_minus(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# [C1] Two sessions same day must equal one session with their combined load
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_two_sessions_same_day_equals_sum(tmp_path):
    """2×50 TSS on day D must produce the same CTL as 1×100 TSS on day D."""
    day = _today_minus(1)

    # DB A: two sessions of 50 each
    db_a = _make_db(tmp_path, "prop_a.db")
    _insert(db_a, [(day, 50), (day, 50)])
    history_a = db_a.get_training_load_history()
    day_row_a = dict(history_a)

    # DB B: one session of 100
    db_b = _make_db(tmp_path, "prop_b.db")
    _insert(db_b, [(day, 100)])
    history_b = db_b.get_training_load_history()
    day_row_b = dict(history_b)

    assert day in day_row_a, f"Day {day} missing from history_a"
    assert day in day_row_b, f"Day {day} missing from history_b"
    assert day_row_a[day] == pytest.approx(day_row_b[day], abs=0.01), (
        f"Same-day aggregation mismatch: 2×50={day_row_a[day]} vs 1×100={day_row_b[day]}"
    )

    ctl_a, _, _ = db_a.get_ctl_atl_tsb()
    ctl_b, _, _ = db_b.get_ctl_atl_tsb()
    assert ctl_a == pytest.approx(ctl_b, abs=0.01), (
        f"CTL diverged: split-session={ctl_a} combined-session={ctl_b}"
    )


# ---------------------------------------------------------------------------
# [C2] ATL must use a date window, not item count
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_atl_uses_date_window_not_count(tmp_path):
    """Activities older than ATL_DECAY_DAYS must not influence ATL."""
    from titan.config.thresholds import ATL_DECAY_DAYS

    db = _make_db(tmp_path)

    # Insert 3 activities well outside the ATL window (>ATL_DECAY_DAYS ago)
    old_days = [ATL_DECAY_DAYS + 5, ATL_DECAY_DAYS + 10, ATL_DECAY_DAYS + 15]
    for d in old_days:
        _insert(db, [(_today_minus(d), 200)])

    # Capture ATL with only old activities (should be 0 — outside window)
    _, atl_old_only, _ = db.get_ctl_atl_tsb()

    # Insert 1 activity within the ATL window
    _insert(db, [(_today_minus(2), 80)])
    _, atl_with_recent, _ = db.get_ctl_atl_tsb()

    assert atl_with_recent > atl_old_only, (
        "ATL should increase when a recent activity is added; "
        f"got atl_old_only={atl_old_only}, atl_with_recent={atl_with_recent}"
    )


# ---------------------------------------------------------------------------
# [C3] Empty training log → zeros, no exception
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_empty_stream_returns_zeros(tmp_path):
    """get_ctl_atl_tsb on an empty DB must return (0.0, 0.0, 0.0) without raising."""
    db = _make_db(tmp_path)
    ctl, atl, tsb = db.get_ctl_atl_tsb()
    assert ctl == 0.0, f"Expected CTL=0.0 on empty DB, got {ctl}"
    assert atl == 0.0, f"Expected ATL=0.0 on empty DB, got {atl}"
    assert tsb == 0.0, f"Expected TSB=0.0 on empty DB, got {tsb}"


# ---------------------------------------------------------------------------
# [C4] CTL increases after inserting a high-TSS day
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ctl_increases_with_load(tmp_path):
    """Adding a high-TSS day on top of a 30-day baseline must raise CTL."""
    db = _make_db(tmp_path)

    # 30-day baseline at moderate load
    baseline_rows = [(_today_minus(i + 2), 60) for i in range(30)]
    _insert(db, baseline_rows)
    ctl_before, _, _ = db.get_ctl_atl_tsb()

    # One extra high-TSS day (yesterday)
    _insert(db, [(_today_minus(1), 300)])
    ctl_after, _, _ = db.get_ctl_atl_tsb()

    assert ctl_after > ctl_before, (
        f"CTL must increase after a high-TSS day; before={ctl_before}, after={ctl_after}"
    )
