"""The worker builds the weekly plan every Sunday and keeps it in the database (D-020)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import titan.worker as worker
from titan.core.database import DatabaseManager

SUNDAY = date(2026, 10, 11)
WEDNESDAY = date(2026, 10, 7)


class _Planner:
    """Stands in for WeeklyPlanGenerator: records every plan it is asked for."""

    def __init__(self, week_start: str) -> None:
        self.week_start = week_start
        self.generated = 0
        self.last_plan = None

    def generate_weekly_plan(self, athlete_profile: dict, phase: str = "BUILD") -> dict:
        self.generated += 1
        plan = {"week_start": self.week_start, "phase": phase, "daily_sessions": [{"day": "Monday"}]}
        self.last_plan = plan
        return plan


class _Telegram:
    def __init__(self) -> None:
        self.plans: list[dict] = []

    def send_weekly_plan(self, plan: dict) -> bool:
        self.plans.append(plan)
        return True


def _coach(week_start: str) -> SimpleNamespace:
    return SimpleNamespace(weekly_planner=_Planner(week_start), telegram=_Telegram())


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_name="weekly_plan.db", db_dir=tmp_path)
    yield manager
    manager.close()


@pytest.mark.unit
def test_latest_plan_is_the_newest_week_on_or_before_the_date(db):
    db.save_weekly_plan(athlete_id="owner", week_start="2026-10-05", plan={"week_start": "2026-10-05", "v": 1})
    db.save_weekly_plan(athlete_id="owner", week_start="2026-10-12", plan={"week_start": "2026-10-12", "v": 1})
    db.save_weekly_plan(athlete_id="owner", week_start="2026-10-05", plan={"week_start": "2026-10-05", "v": 2})

    assert db.get_latest_weekly_plan(athlete_id="owner", on_or_before="2026-10-11") == {
        "week_start": "2026-10-05", "v": 2,
    }
    assert db.get_latest_weekly_plan(athlete_id="owner", on_or_before="2026-10-12")["week_start"] == "2026-10-12"
    assert db.get_latest_weekly_plan(athlete_id="owner", on_or_before="2026-10-04") is None
    assert db.get_latest_weekly_plan(athlete_id="other", on_or_before="2026-10-12") is None


@pytest.mark.unit
def test_stored_plan_of_this_week_is_loaded_without_a_new_one(db):
    stored = {"week_start": "2026-10-05", "daily_sessions": [{"day": "Wednesday", "session_type": "TEMPO"}]}
    db.save_weekly_plan(athlete_id="owner", week_start="2026-10-05", plan=stored)
    coach = _coach("2026-10-08")

    worker._prepare_weekly_plan(coach, db, "owner", WEDNESDAY)

    assert coach.weekly_planner.last_plan == stored
    assert coach.weekly_planner.generated == 0
    assert coach.telegram.plans == []


@pytest.mark.unit
def test_without_a_plan_for_this_week_one_is_built_stored_and_sent(db):
    db.save_weekly_plan(athlete_id="owner", week_start="2026-09-28", plan={"week_start": "2026-09-28"})
    coach = _coach("2026-10-08")

    worker._prepare_weekly_plan(coach, db, "owner", WEDNESDAY)

    assert coach.weekly_planner.generated == 1
    assert [p["week_start"] for p in coach.telegram.plans] == ["2026-10-08"]
    assert db.get_latest_weekly_plan(athlete_id="owner", on_or_before="2026-10-08")["week_start"] == "2026-10-08"


@pytest.mark.unit
def test_sunday_builds_next_weeks_plan_once(db):
    coach = _coach("2026-10-12")

    worker._plan_next_week_on_sunday(coach, db, "owner", SUNDAY)
    worker._plan_next_week_on_sunday(coach, db, "owner", SUNDAY)

    assert coach.weekly_planner.generated == 1
    assert len(coach.telegram.plans) == 1
    assert db.get_latest_weekly_plan(athlete_id="owner", on_or_before="2026-10-12")["week_start"] == "2026-10-12"


@pytest.mark.unit
def test_other_days_do_not_build_next_weeks_plan(db):
    coach = _coach("2026-10-08")

    worker._plan_next_week_on_sunday(coach, db, "owner", WEDNESDAY)

    assert coach.weekly_planner.generated == 0


@pytest.mark.unit
def test_a_failing_plan_is_logged_and_the_morning_goes_on(db, caplog):
    coach = SimpleNamespace(weekly_planner=SimpleNamespace(last_plan=None), telegram=_Telegram())

    worker._prepare_weekly_plan(coach, db, "owner", WEDNESDAY)
    worker._plan_next_week_on_sunday(coach, db, "owner", SUNDAY)

    assert [r.message for r in caplog.records].count("worker_weekly_plan_failed") == 2
    assert coach.weekly_planner.last_plan is None


@pytest.mark.unit
def test_worker_morning_runs_plan_routine_then_sunday_plan(db, monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(worker, "_build_daily_coach", lambda _db, athlete_id="owner": SimpleNamespace(
        run_morning_routine=lambda: order.append("routine"),
    ))
    monkeypatch.setattr(worker, "_prepare_weekly_plan", lambda *a: order.append("this_week"))
    monkeypatch.setattr(worker, "_plan_next_week_on_sunday", lambda *a: order.append("next_week"))

    worker._run_morning(db)

    assert order == ["this_week", "routine", "next_week"]
