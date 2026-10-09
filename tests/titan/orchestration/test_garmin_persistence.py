"""Garmin persistence moved out of DailyCoach (plan task 6, D-029)."""
from __future__ import annotations

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration import daily_coach
from titan.orchestration.garmin_persistence import PersistenceFailure, persist_garmin_data

DAY = "2026-03-04"


def _payload() -> dict:
    return {
        "activities": [{
            "activity_id": "garmin-1", "date": DAY, "activity_type": "running",
            "distance_km": 8, "duration_sec": 2700, "name": "AM",
        }],
        "sleep": [{"date": DAY, "resting_hr": 48, "sleep_score": 82, "total_sleep_hours": 7.2}],
        "hrv": [{"date": DAY, "rmssd": 55.0}],
        "weight": [],
    }


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_name="garmin_persistence.db", db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
def test_persist_stores_the_sync_for_the_given_athlete_and_reports_through_emit(db):
    events: list[str] = []

    result = persist_garmin_data(
        db, _payload(), DAY, athlete_id="owner", emit=lambda action, **_f: events.append(action),
    )

    assert result == (48, 82, 7.2)
    row = db.conn.execute(
        "SELECT athlete_id, resting_hr, sleep_quality, sleep_hours, hrv_rmssd FROM daily_metrics WHERE date = ?", (DAY,),
    ).fetchone()
    assert tuple(row) == ("owner", 48, 82, 7.2, 55.0)
    session = db.conn.execute("SELECT session_type FROM training_log WHERE date = ?", (DAY,)).fetchone()
    assert session[0] == "EASY"
    assert events[-1] == "daily_metrics_persisted"
    assert "activities_persisted" in events


@pytest.mark.unit
def test_rolled_back_transaction_raises_with_the_decision_values(db, monkeypatch):
    def _fail(**_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "save_daily_metric", _fail)
    events: list[str] = []

    with pytest.raises(PersistenceFailure) as excinfo:
        persist_garmin_data(db, _payload(), DAY, athlete_id="owner", emit=lambda a, **_f: events.append(a))

    assert (excinfo.value.today_rhr, excinfo.value.today_sleep_score, excinfo.value.today_sleep_hours) == (48, 82, 7.2)
    assert events[-1] == "daily_metrics_persist_failed"
    assert db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()[0] == 0


@pytest.mark.unit
def test_daily_coach_delegates_and_keeps_its_names(db, monkeypatch):
    """DailyCoach still exposes the moved names, and its events still go through _daily_coach_event."""
    assert daily_coach.PersistenceFailure is PersistenceFailure
    assert daily_coach._GARMIN_ACTIVITY_TYPE_MAP["interval_training"] == "INTERVALS"
    events: list[str] = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **_f: events.append(action))
    coach = daily_coach.DailyCoach.__new__(daily_coach.DailyCoach)
    coach.db = db
    coach.athlete_id = "owner"

    assert coach._persist_garmin_data(_payload(), DAY) == (48, 82, 7.2)
    assert events[-1] == "daily_metrics_persisted"
