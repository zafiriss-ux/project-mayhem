"""M0-11: the RHR baseline counts back from the morning's day, not from the clock.

A morning for day D can run after midnight (the worker retries a claimed day, D-109).
Before the fix the baseline window was the 7 days before the clock's today, D+1, so it
held day D itself: the RHR spike H3 should catch diluted its own baseline (the rule of
D-105 / SG-06), and the oldest day of the real window was dropped.

Example: 50 bpm for a week, 80 bpm on D. For D the baseline is 50, so H3 sees +30.
The old window gave (6 × 50 + 80) / 7 = 54.3.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tests.titan.core.test_persistence import _build_test_engine
from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DailyCoach

_USUAL_RHR = 50
_SPIKE_RHR = 80


def _yesterday() -> date:
    return datetime.now(UTC).date() - timedelta(days=1)


def _save_week_and_spike(save, day: date) -> None:
    """50 bpm on the 7 days before *day*, 80 bpm on *day*, and 50 again on the day after."""
    for back in range(1, 8):
        save((day - timedelta(days=back)).isoformat(), rhr=_USUAL_RHR)
    save(day.isoformat(), rhr=_SPIKE_RHR)
    save((day + timedelta(days=1)).isoformat(), rhr=_USUAL_RHR)


@pytest.fixture
def db(tmp_path: Path):
    manager = DatabaseManager("titan_core.db", db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
def test_baseline_for_a_past_day_leaves_out_that_day_and_later_days(db) -> None:
    day = _yesterday()
    _save_week_and_spike(db.save_daily_metric, day)

    assert db.get_baseline_rhr(days=7, before_date=day.isoformat()) == pytest.approx(_USUAL_RHR)


@pytest.mark.unit
def test_baseline_without_a_day_still_counts_back_from_today(db) -> None:
    day = _yesterday()
    _save_week_and_spike(db.save_daily_metric, day)

    # Today's window is the 7 days before today: six days at 50 and yesterday's 80.
    expected = round((6 * _USUAL_RHR + _SPIKE_RHR) / 7, 1)
    assert db.get_baseline_rhr(days=7) == pytest.approx(expected)


@pytest.mark.unit
def test_a_morning_replayed_after_midnight_uses_the_week_before_its_own_day(db) -> None:
    """The real path: DailyCoach reads the baseline for its claimed day (D-109)."""
    day = _yesterday()
    _save_week_and_spike(db.save_daily_metric, day)
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = db
    coach.athlete_id = "owner"
    coach.routine_date = day.isoformat()

    assert coach._get_baseline_rhr(days=7) == pytest.approx(_USUAL_RHR)


@pytest.mark.unit
def test_a_morning_without_a_claimed_day_uses_the_week_before_today(db) -> None:
    day = _yesterday()
    _save_week_and_spike(db.save_daily_metric, day)
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = db
    coach.athlete_id = "owner"
    coach.routine_date = None

    expected = round((6 * _USUAL_RHR + _SPIKE_RHR) / 7, 1)
    assert coach._get_baseline_rhr(days=7) == pytest.approx(expected)


@pytest.mark.integration
def test_postgres_adapter_baseline_for_a_past_day_leaves_out_that_day() -> None:
    _engine, adapter = _build_test_engine()
    try:
        day = _yesterday()
        _save_week_and_spike(adapter.save_daily_metric, day)

        assert adapter.get_baseline_rhr(days=7, before_date=day.isoformat()) == pytest.approx(
            _USUAL_RHR
        )
    finally:
        adapter.close()
