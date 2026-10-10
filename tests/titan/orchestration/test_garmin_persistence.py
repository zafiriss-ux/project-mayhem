"""Garmin persistence moved out of DailyCoach (plan task 6, D-029)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration import daily_coach
from titan.orchestration.garmin_persistence import (
    PersistenceFailure,
    backfill_training_history,
    persist_garmin_data,
)

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


@pytest.mark.unit
def test_values_in_the_wrong_unit_are_stored_with_a_quality_flag(db):
    """SV-17: a run timed in minutes and sleep in the wrong unit are kept, but flagged."""
    payload = _payload()
    payload["activities"][0].update(distance_km=7.27, duration_sec=40)
    payload["sleep"][0]["total_sleep_hours"] = 0.12

    persist_garmin_data(db, payload, DAY, athlete_id="owner", emit=lambda *_a, **_f: None)

    run_flag = db.conn.execute("SELECT quality_flag FROM training_log WHERE date = ?", (DAY,)).fetchone()[0]
    day_flag = db.conn.execute("SELECT quality_flag FROM daily_metrics WHERE date = ?", (DAY,)).fetchone()[0]
    assert run_flag == "degraded"
    assert day_flag == "degraded"


def _today() -> str:
    # The load-history query reads SQLite's own clock, so these tests use the real date.
    return datetime.now(UTC).date().isoformat()


class _HistoryGarmin:
    """Serves activities by age in days; records how far back it was asked."""

    athlete_max_hr = 0

    def __init__(self, ages: list[int]) -> None:
        self.ages = ages
        self.calls: list[int] = []

    def sync_activities(self, days_back: int, athlete_max_hr: int = 0) -> list[dict]:
        self.calls.append(days_back)
        today = date.fromisoformat(_today())
        return [{
            "activity_id": f"garmin-old-{age}", "date": (today - timedelta(days=age)).isoformat(),
            "activity_type": "running", "distance_km": 10, "duration_sec": 3300,
            "estimated_training_load": 80, "name": "old",
        } for age in self.ages if age <= days_back]


@pytest.mark.unit
def test_short_history_is_backfilled_from_garmin(db):
    """D-055: with no session older than 42 days, 210 days of activities are fetched once."""
    from titan.science.tsb_engine import LOAD_HISTORY_DAYS

    garmin = _HistoryGarmin([3, 60, 150, 300])
    events: list[str] = []

    count = backfill_training_history(db, garmin, _today(), athlete_id="owner", emit=lambda a, **_f: events.append(a))

    assert garmin.calls == [LOAD_HISTORY_DAYS]
    assert count == 3
    dates = [r[0] for r in db.conn.execute("SELECT date FROM training_log ORDER BY date")]
    today = date.fromisoformat(_today())
    assert dates == [(today - timedelta(days=age)).isoformat() for age in (150, 60, 3)]
    assert events[-1] == "training_history_backfilled"


@pytest.mark.unit
def test_long_enough_history_is_not_fetched_again(db):
    garmin = _HistoryGarmin([60])
    backfill_training_history(db, garmin, _today(), athlete_id="owner", emit=lambda *_a, **_f: None)

    count = backfill_training_history(db, garmin, _today(), athlete_id="owner", emit=lambda *_a, **_f: None)

    assert count == 0
    assert len(garmin.calls) == 1
