"""AT-02: the e2e Garmin stub returns what GarminSync.sync_all() returns.

The old stub sent undated raw-Garmin sleep (restingHeartRate, sleepScores),
activities with session_type/name instead of activity_type, and 12 top-level
keys the real sync never emits. Undated sleep sends garmin_persistence down the
legacy "last entry wins" branch, which the real sync never takes, so the gold
path did not cover how today's sleep is read.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.e2e.conftest import E2E_TODAY, StubGarminSync
from titan.orchestration.contracts import GarminSyncResult

# Keys sync_sleep() / sync_activities() put in each record (garmin_sync.py).
SLEEP_KEYS = {
    "date", "total_sleep_hours", "deep_sleep_hours", "rem_sleep_hours", "sleep_score", "resting_hr",
}
ACTIVITY_KEYS = {
    "date", "activity_type", "distance_km", "duration_sec", "avg_hr", "max_hr",
    "avg_pace_sec_per_km", "calories", "elevation_gain_m", "activity_id",
    "training_effect_label", "estimated_training_load", "load_estimated",
}


def test_top_level_keys_are_those_of_the_sync_contract() -> None:
    payload = StubGarminSync(today=E2E_TODAY).sync_all()
    assert set(payload) <= set(GarminSyncResult.__annotations__)
    assert {"activities", "weight", "sleep", "hrv", "hrv_sync_metrics"} <= set(payload)


def test_records_have_the_keys_the_real_sync_emits() -> None:
    payload = StubGarminSync(today=E2E_TODAY).sync_all()
    assert payload["sleep"], "no sleep records"
    assert all(set(entry) == SLEEP_KEYS for entry in payload["sleep"])
    assert payload["activities"], "no activities"
    assert all(set(entry) == ACTIVITY_KEYS for entry in payload["activities"])


@pytest.mark.integration
def test_the_morning_stores_last_nights_sleep_not_an_older_night(morning_routine_setup) -> None:
    coach = morning_routine_setup["coach"]
    db = morning_routine_setup["db"]
    assert coach.run_morning_routine() is True

    yesterday = (date.fromisoformat(E2E_TODAY) - timedelta(days=1)).isoformat()
    rows = {
        row[0]: (row[1], row[2])
        for row in db.conn.execute(
            "SELECT date, sleep_quality, resting_hr FROM daily_metrics WHERE date IN (?, ?)",
            (E2E_TODAY, yesterday),
        )
    }
    # The stub's older night (score 61, RHR 57) comes last in the list, so the
    # legacy last-entry-wins branch would store it for today.
    assert rows[E2E_TODAY] == (82, 50)
