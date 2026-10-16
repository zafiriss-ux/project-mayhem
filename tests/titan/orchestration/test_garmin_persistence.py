"""Garmin persistence moved out of DailyCoach (plan task 6, D-029)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration import daily_coach
from titan.orchestration.garmin_persistence import (
    HRV_REWRITE_MARKER,
    HRV_REWRITE_NIGHTS,
    PersistenceFailure,
    backfill_training_history,
    persist_garmin_data,
    rewrite_recent_hrv_once,
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
def test_an_impossible_activity_date_is_skipped_and_the_sync_keeps_the_rest(db):
    """F3: '2026-09-31' was stored as degraded and get_ctl_atl_tsb then raised for the athlete."""
    payload = _payload()
    payload["activities"].append({
        "activity_id": "garmin-bad", "date": "2026-09-31", "activity_type": "running",
        "distance_km": 5, "duration_sec": 1800, "name": "bad",
    })
    outcomes: list[str] = []

    def _emit(action, **fields):
        if action == "activity_persist" and fields["outcome"].startswith("ACTIVITY_"):
            outcomes.append(fields["outcome"])

    persist_garmin_data(db, payload, DAY, athlete_id="owner", emit=_emit)

    assert outcomes == ["ACTIVITY_PERSISTED", "ACTIVITY_SANITY_REJECTED"]
    dates = [r[0] for r in db.conn.execute("SELECT date FROM training_log").fetchall()]
    assert dates == [DAY]
    ctl, atl, tsb = db.get_ctl_atl_tsb(athlete_id="owner")
    assert all(isinstance(x, float) for x in (ctl, atl, tsb))


@pytest.mark.unit
def test_an_activity_without_a_date_is_rejected_not_reported_as_persisted(db):
    """F1: the row was dropped by INSERT OR IGNORE while the event said ACTIVITY_PERSISTED."""
    payload = _payload()
    payload["activities"].append({
        "activity_id": "garmin-nodate", "date": None, "activity_type": "running",
        "distance_km": 5, "duration_sec": 1800, "name": "no date",
    })
    outcomes: list[str] = []

    def _emit(action, **fields):
        if action == "activity_persist" and fields["outcome"].startswith("ACTIVITY_"):
            outcomes.append(fields["outcome"])

    persist_garmin_data(db, payload, DAY, athlete_id="owner", emit=_emit)

    assert outcomes == ["ACTIVITY_PERSISTED", "ACTIVITY_SANITY_REJECTED"]
    assert db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone() == (1,)


@pytest.mark.unit
def test_a_non_numeric_field_rejects_only_that_activity(db):
    """F2: distance_km="ten" raised in the sanity check and the whole sync rolled back."""
    payload = _payload()
    payload["activities"].append({
        "activity_id": "garmin-bad", "date": DAY, "activity_type": "running",
        "distance_km": "ten", "duration_sec": 1800, "name": "bad",
    })
    outcomes: list[str] = []

    def _emit(action, **fields):
        if action == "activity_persist" and fields["outcome"].startswith("ACTIVITY_"):
            outcomes.append(fields["outcome"])

    persist_garmin_data(db, payload, DAY, athlete_id="owner", emit=_emit)

    assert outcomes == ["ACTIVITY_PERSISTED", "ACTIVITY_SANITY_REJECTED"]
    assert db.conn.execute("SELECT garmin_activity_id FROM training_log").fetchall() == [("garmin-1",)]


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


@pytest.mark.unit
def test_a_load_estimated_without_heart_rate_is_stored_with_a_quality_flag(db):
    """F6: the middle-zone load of a session without HR is kept, but flagged."""
    payload = _payload()
    payload["activities"][0].update(estimated_training_load=135.0, load_estimated=True)

    persist_garmin_data(db, payload, DAY, athlete_id="owner", emit=lambda *_a, **_f: None)

    row = db.conn.execute("SELECT training_load, quality_flag FROM training_log WHERE date = ?", (DAY,)).fetchone()
    assert tuple(row) == (135, "degraded")


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


class _HrvGarmin:
    def __init__(self, nights: dict[str, float]) -> None:
        self.nights = nights
        self.calls: list[int] = []

    def sync_hrv(self, days_back: int) -> list[dict]:
        self.calls.append(days_back)
        return [{"date": d, "rmssd": v, "status": "", "source": "garmin"} for d, v in self.nights.items()]


@pytest.mark.unit
def test_recent_hrv_is_rewritten_once_and_manual_rows_are_kept(db):
    """D-056: the 28 nights stored with lastNight5MinHigh are replaced by lastNightAvg, once."""
    db.save_daily_metric(date="2026-03-01", hrv=66.0, athlete_id="owner")
    db.save_daily_metric(date="2026-03-02", hrv=70.0, data_source="manual_entry", athlete_id="owner")
    garmin = _HrvGarmin({"2026-03-01": 52.0, "2026-03-02": 50.0, "2026-03-03": 49.0})
    events: list[str] = []

    rewritten = rewrite_recent_hrv_once(db, garmin, athlete_id="owner", emit=lambda a, **_f: events.append(a))
    again = rewrite_recent_hrv_once(db, garmin, athlete_id="owner", emit=lambda a, **_f: events.append(a))

    rows = dict(db.conn.execute("SELECT date, hrv_rmssd FROM daily_metrics ORDER BY date").fetchall())
    assert rows == {"2026-03-01": 52.0, "2026-03-02": 70.0, "2026-03-03": 49.0}
    assert (rewritten, again) == (3, 0)
    assert garmin.calls == [HRV_REWRITE_NIGHTS]
    assert events == ["hrv_history_rewritten"]


@pytest.mark.unit
def test_hrv_rewrite_waits_for_a_morning_with_garmin_data(db):
    garmin = _HrvGarmin({})

    assert rewrite_recent_hrv_once(db, garmin, athlete_id="owner", emit=lambda *_a, **_f: None) == 0
    assert db.get_last_sync_outcome(HRV_REWRITE_MARKER) is None
