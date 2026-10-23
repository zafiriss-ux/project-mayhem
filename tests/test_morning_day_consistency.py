"""OW-L5 14β (D-131): one day and one clock for the morning's inputs.

- The HRV log is kept in date order, so the latest reading and the baseline window are
  the most recent by date, whatever order a sync added them in.
- TSB is computed for the morning's own day, not the clock's (a morning claimed for one
  day can run after midnight, D-109).
- An activity's day is its UTC day (Garmin's ``startTimeGMT``), as sleep, HRV and the
  morning are; ``startTimeLocal`` is only the fallback.
Synthetic data only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from titan.integrations import garmin_sync
from titan.science import tsb_engine
from titan.science.hrv_engine import HRVGuidedEngine as HRVEngine
from titan.science.tsb_engine import TSBEngine


def test_a_reading_added_out_of_order_does_not_become_the_latest():
    hrv = HRVEngine()
    for day, value in [("2026-10-10", 50.0), ("2026-10-11", 51.0), ("2026-10-14", 60.0), ("2026-10-12", 40.0)]:
        hrv.add_hrv_measurement(day, value)
    assert hrv.get_hrv_summary()["latest_hrv"] == 60.0
    assert hrv.get_latest_hrv() == 60.0
    assert [d for d, _ in hrv.hrv_log] == ["2026-10-10", "2026-10-11", "2026-10-12", "2026-10-14"]


def test_the_baseline_window_is_the_most_recent_days():
    hrv = HRVEngine(baseline_days=2)
    for day, value in [("2026-10-12", 40.0), ("2026-10-13", 42.0), ("2026-10-01", 90.0)]:
        hrv.add_hrv_measurement(day, value)
    baseline, _sd = hrv.calculate_baseline(2)
    assert baseline == 41.0


def test_a_later_reading_of_the_same_day_still_replaces_the_earlier_one():
    hrv = HRVEngine()
    hrv.add_hrv_measurement("2026-10-14", 55.0)
    hrv.add_hrv_measurement("2026-10-14", 57.0)
    assert hrv.hrv_log == [("2026-10-14", 57.0)]


def test_tsb_is_computed_for_the_given_day(monkeypatch):
    monkeypatch.setattr(tsb_engine, "_today", lambda: date(2026, 10, 15))
    engine = TSBEngine()
    for day in range(1, 15):
        engine.add_daily_load(f"2026-10-{day:02d}", 80.0)
    after_midnight = engine.calculate_tsb()[0]
    engine.reference_date = date(2026, 10, 14)
    on_the_day = engine.calculate_tsb()[0]
    # A day later the 15th counts as a rest day; on the morning's own day it does not.
    assert on_the_day != after_midnight
    # The same as computing it on the 14th itself.
    monkeypatch.setattr(tsb_engine, "_today", lambda: date(2026, 10, 14))
    engine.reference_date = None
    assert on_the_day == engine.calculate_tsb()[0]


def test_the_morning_hands_its_day_to_the_tsb_engine():
    from titan.orchestration.daily_coach import _routine_day

    class _Coach:
        routine_date = "2026-10-14"

    assert _routine_day(_Coach()) == date(2026, 10, 14)
    from titan.orchestration import daily_coach

    source = Path(daily_coach.__file__).read_text(encoding="utf-8")
    assert "self.tsb.reference_date = _routine_day(self)" in source


@pytest.mark.parametrize(("raw", "expected"), [
    # Late evening in Athens (+03:00): local day 14, UTC day 14.
    ({"startTimeLocal": "2026-10-14 22:30:00", "startTimeGMT": "2026-10-14 19:30:00"}, "2026-10-14"),
    # Just after midnight in Athens: local day 15, UTC day 14, as sleep and HRV count it.
    ({"startTimeLocal": "2026-10-15 00:30:00", "startTimeGMT": "2026-10-14 21:30:00"}, "2026-10-14"),
    # Without startTimeGMT the local time is the fallback, as before.
    ({"startTimeLocal": "2026-10-15 00:30:00"}, "2026-10-15"),
    ({"startTimeLocal": "2026-10-15T00:30:00+03:00"}, "2026-10-14"),
])
def test_an_activity_is_dated_by_its_utc_day(raw, expected):
    assert garmin_sync._activity_day(raw) == expected


def test_today_is_utc():
    assert tsb_engine._today() == datetime.now(UTC).date()
