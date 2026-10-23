"""OW-F2 / P4-07 (ADR-0069 §2): the fatigue of ``/manual_entry`` reaches H5.

- A fatigue entered after the morning sync created the day's row is stored (the upsert kept
  the old, empty value).
- The morning (worker and ``/today``) reads the athlete's stored fatigue: the morning's own
  day, else the evening before. With none stored the score stays 3 (D-043).
- One scale everywhere: 0-10.
Synthetic data only.
"""

from __future__ import annotations

from datetime import timedelta

from tests.test_daily_coach_characterization import (  # noqa: F401  (world is a fixture)
    START_DAY,
    _run_scenario,
    normal_day,
    world,
)
from titan.core.database import DatabaseManager


def _h5_events(day: dict) -> list[dict]:
    return [e for e in day["events"] if e.get("governance_gate") == "H5"]


def test_a_fatigue_entered_after_the_sync_is_stored(tmp_path):
    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    db.save_daily_metric(date="2026-03-04", hrv=60.0, rhr=50, data_source="garmin_api")
    db.save_daily_metric(date="2026-03-04", fatigue=9, data_source="manual_entry")
    row = db.get_daily_metric("2026-03-04")
    assert row is not None
    assert row["fatigue_level"] == 9
    assert row["hrv_rmssd"] == 60.0  # the manual entry does not clear the sync's values


def test_a_garmin_resync_keeps_the_manual_fatigue(tmp_path):
    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    db.save_daily_metric(date="2026-03-04", fatigue=7, data_source="manual_entry")
    db.save_daily_metric(date="2026-03-04", hrv=61.0, data_source="garmin_api")
    assert db.get_daily_metric("2026-03-04")["fatigue_level"] == 7


def test_the_evening_fatigue_reaches_h5_the_next_morning(world):
    evening = (START_DAY + timedelta(days=1)).isoformat()

    def before_morning(index: int, db: DatabaseManager) -> None:
        if index == 2:  # sent the evening before morning 2: /manual_entry FATIGUE=9
            db.save_daily_metric(date=evening, fatigue=9, data_source="manual_entry")

    result = _run_scenario(world, [normal_day(i) for i in range(3)], before_morning=before_morning)
    events = _h5_events(result["days"][2])
    assert events, "H5 did not fire on the morning after FATIGUE=9"
    assert events[0]["action"] == "EASY"
    assert events[0]["subjective_fatigue"] == 9


def test_the_morning_fatigue_of_the_same_day_counts(world):
    morning = (START_DAY + timedelta(days=2)).isoformat()

    def before_morning(index: int, db: DatabaseManager) -> None:
        if index == 2:
            db.save_daily_metric(date=morning, fatigue=8, data_source="manual_entry")

    result = _run_scenario(world, [normal_day(i) for i in range(3)], before_morning=before_morning)
    events = _h5_events(result["days"][2])
    assert events and events[0]["subjective_fatigue"] == 8


def test_without_an_entry_the_score_stays_3(world):
    result = _run_scenario(world, [normal_day(i) for i in range(3)])
    assert not any(_h5_events(day) for day in result["days"])
    assert not any(
        e.get("governance_gate") == "H5_FATIGUE" for day in result["days"] for e in day["events"]
    ), "no entry is the D-043 default 3, not missing fatigue"
