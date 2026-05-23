"""TD-CTL-03: Deterministic TSB replay harness tests."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from titan.core.database import DatabaseManager


def _make_db(tmp_path: Path, name: str = "replay.db") -> DatabaseManager:
    return DatabaseManager(db_name=name, db_dir=tmp_path)


def _insert(db: DatabaseManager, date_str: str, load: int, athlete_id: str = "owner") -> None:
    db.save_session(
        date=date_str,
        session_type="EASY",
        distance_km=10.0,
        duration_sec=3600,
        training_load=load,
        athlete_id=athlete_id,
    )


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _days_ahead(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def test_replay_is_deterministic(tmp_path):
    """Two calls with same athlete_id and as_of_date return identical (ctl, atl, tsb)."""
    db = _make_db(tmp_path)
    _insert(db, _days_ago(5), 80)
    _insert(db, _days_ago(10), 60)

    today = date.today()
    assert db.replay_tsb("owner", today) == db.replay_tsb("owner", today)


def test_replay_excludes_future_data(tmp_path):
    """Activity on D+10 must not affect replay at D."""
    today = date.today()

    db_with_future = _make_db(tmp_path, "with_future.db")
    _insert(db_with_future, _days_ago(3), 75)
    _insert(db_with_future, _days_ahead(10), 200)

    db_clean = _make_db(tmp_path, "clean.db")
    _insert(db_clean, _days_ago(3), 75)

    ctl_with_future, _, _ = db_with_future.replay_tsb("owner", today)
    ctl_clean, _, _ = db_clean.replay_tsb("owner", today)

    assert ctl_with_future == pytest.approx(ctl_clean, abs=0.1)


def test_replay_matches_current_for_today(tmp_path):
    """replay_tsb(today) must match get_ctl_atl_tsb() within rounding tolerance."""
    db = _make_db(tmp_path)
    _insert(db, _days_ago(1), 90)
    _insert(db, _days_ago(3), 70)
    _insert(db, _days_ago(7), 50)

    replay_ctl, replay_atl, replay_tsb_val = db.replay_tsb("owner", date.today())
    current_ctl, current_atl, current_tsb = db.get_ctl_atl_tsb("owner")

    assert replay_ctl == pytest.approx(current_ctl, abs=0.1)
    assert replay_atl == pytest.approx(current_atl, abs=0.1)
    assert replay_tsb_val == pytest.approx(current_tsb, abs=0.1)


def test_replay_empty_returns_zeros(tmp_path):
    """Empty DB → replay returns (0.0, 0.0, 0.0) for any date."""
    db = _make_db(tmp_path)
    assert db.replay_tsb("owner", date.today()) == (0.0, 0.0, 0.0)
    assert db.replay_tsb("owner", date(2020, 1, 1)) == (0.0, 0.0, 0.0)
