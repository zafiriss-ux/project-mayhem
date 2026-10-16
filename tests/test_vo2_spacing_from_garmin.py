"""D-089: the V5 gate sees the days since the last VO2 session.

Before, every Garmin run was stored as EASY (SV-11) and ``days_since_last_vo2``
was never filled (SV-15), so V5 (two days between VO2 sessions) never ran.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

import titan.integrations.garmin_sync as gs_mod
from titan.core.database import DatabaseManager
from titan.integrations.garmin_sync import GarminSync
from titan.orchestration.daily_coach import DailyCoach
from titan.orchestration.garmin_persistence import _label_session_type, persist_garmin_data
from titan.science.governance_engine import GovernanceEngine


def _day(days_ago: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_name="vo2_spacing.db", db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
@pytest.mark.parametrize("label,expected", [
    ("VO2MAX", "INTERVALS"), ("VO2_MAX", "INTERVALS"), ("ANAEROBIC_CAPACITY", "INTERVALS"),
    ("SPRINT", "INTERVALS"), ("TEMPO", "TEMPO"), ("LACTATE_THRESHOLD", "TEMPO"),
    ("AEROBIC_BASE", None), ("RECOVERY", None), (None, None), ("", None),
])
def test_the_training_effect_label_gives_the_session_type(label, expected) -> None:
    assert _label_session_type(label) == expected


@pytest.mark.unit
def test_the_sync_keeps_the_training_effect_label(monkeypatch) -> None:
    sync = GarminSync(email="test@example.com", password="secret")
    sync.is_connected = True
    sync.client = MagicMock()
    monkeypatch.setattr(gs_mod, "_garmin_event", lambda *a, **kw: None)
    sync.client.get_activities_by_date = MagicMock(return_value=[{
        "startTimeLocal": "2026-10-15T07:00:00", "activityType": {"typeKey": "running"},
        "duration": 2400, "distance": 8000, "averageHR": 165, "maxHR": 185,
        "activityId": 42, "trainingEffectLabel": "VO2MAX",
    }])

    activities = sync.sync_activities(days_back=1)

    assert activities[0]["training_effect_label"] == "VO2MAX"


@pytest.mark.unit
def test_a_vo2_run_is_stored_as_intervals_and_an_easy_run_stays_easy(db) -> None:
    payload = {
        "activities": [
            {"activity_id": "g-1", "date": _day(1), "activity_type": "running",
             "distance_km": 8, "duration_sec": 2400, "training_effect_label": "VO2MAX"},
            {"activity_id": "g-2", "date": _day(2), "activity_type": "running",
             "distance_km": 10, "duration_sec": 3300, "training_effect_label": "AEROBIC_BASE"},
        ],
        "sleep": [], "hrv": [], "weight": [],
    }

    persist_garmin_data(db, payload, _day(0), athlete_id="owner", emit=lambda *a, **k: None)

    rows = dict(db.conn.execute("SELECT date, session_type FROM training_log").fetchall())
    assert rows == {_day(1): "INTERVALS", _day(2): "EASY"}


def _coach(db) -> DailyCoach:
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = db
    coach.athlete_id = "owner"
    return coach


@pytest.mark.unit
def test_days_since_last_vo2_come_from_the_stored_history(db) -> None:
    db.save_session(_day(3), "INTERVALS", 8.0, 2400)
    db.save_session(_day(1), "EASY", 10.0, 3300)
    assert _coach(db)._days_since_last_vo2({}) == 3

    db.save_session(_day(0), "INTERVALS", 6.0, 1800)
    assert _coach(db)._days_since_last_vo2({}) == 0


@pytest.mark.unit
def test_no_vo2_session_leaves_the_gate_off(db) -> None:
    db.save_session(_day(1), "EASY", 10.0, 3300)
    assert _coach(db)._days_since_last_vo2({}) is None
    assert _coach(None)._days_since_last_vo2({}) is None


@pytest.mark.unit
def test_a_value_already_in_the_sync_wins(db) -> None:
    db.save_session(_day(1), "INTERVALS", 8.0, 2400)
    assert _coach(db)._days_since_last_vo2({"days_since_last_vo2": 5}) == 5


@pytest.mark.unit
def test_intervals_the_day_after_a_vo2_run_become_tempo(db) -> None:
    db.save_session(_day(1), "INTERVALS", 8.0, 2400)
    days = _coach(db)._days_since_last_vo2({})
    context = {
        "acwr": 1.0, "readiness_score": 80.0, "glycogen_debt": 0.0, "fatigue_level": "LOW",
        "esi_level": "LOW", "days_since_last_vo2": days,
    }

    result = GovernanceEngine()._check_vo2_eligibility(
        {"session_type": "INTERVALS", "zone": 5}, context,
    )

    assert result is not None and result["downgraded_to"] == "TEMPO"
    assert result["failed_conditions"] == ["V5"]
