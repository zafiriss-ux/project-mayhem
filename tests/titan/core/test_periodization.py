from datetime import datetime, timedelta

import pytest

from titan.core.periodization import PeriodizationManager


class _AthleteProfileStub:
    def __init__(self):
        self.current_goal = None
        self.race_day = None
        self.target_time = None


class _FrozenDateTime:
    frozen_now = datetime(2026, 1, 1, 12, 0, 0)

    @classmethod
    def now(cls, tz=None):
        return cls.frozen_now

    @classmethod
    def strptime(cls, value, fmt):
        return datetime.strptime(value, fmt)


@pytest.mark.integration
def test_calculate_phase_boundaries(monkeypatch):
    import titan.core.periodization as periodization_module

    monkeypatch.setattr(periodization_module, "datetime", _FrozenDateTime)
    manager = PeriodizationManager(_AthleteProfileStub())
    now = _FrozenDateTime.now()

    assert manager.calculate_phase(now - timedelta(days=1)) == "POST_RACE"
    assert manager.calculate_phase(now) == "TAPER"
    assert manager.calculate_phase(now + timedelta(days=10)) == "TAPER"
    assert manager.calculate_phase(now + timedelta(days=11)) == "PEAK"
    assert manager.calculate_phase(now + timedelta(days=35)) == "PEAK"
    assert manager.calculate_phase(now + timedelta(days=36)) == "BUILD"
    assert manager.calculate_phase(now + timedelta(days=70)) == "BUILD"
    assert manager.calculate_phase(now + timedelta(days=71)) == "BASE"


@pytest.mark.integration
def test_calculate_phase_is_deterministic_for_same_input(monkeypatch):
    import titan.core.periodization as periodization_module

    monkeypatch.setattr(periodization_module, "datetime", _FrozenDateTime)
    manager = PeriodizationManager(_AthleteProfileStub())
    race_date = _FrozenDateTime.now() + timedelta(days=36)

    assert manager.calculate_phase(race_date) == manager.calculate_phase(race_date)


@pytest.mark.integration
def test_add_goal_sets_current_goal_and_updates_athlete(monkeypatch):
    import titan.core.periodization as periodization_module

    monkeypatch.setattr(periodization_module, "datetime", _FrozenDateTime)
    athlete = _AthleteProfileStub()
    manager = PeriodizationManager(athlete)

    goal = manager.add_goal(21.1, "1:30:00", "2026-04-26")

    assert goal in manager.goals
    assert manager.current_goal == goal
    assert goal["status"] == "ACTIVE"
    assert goal["race_date"] == datetime(2026, 4, 26)
    assert goal["goal_id"].startswith("GOAL_20260101120000")
    assert athlete.current_goal == "21.1K in 1:30:00"
    assert athlete.race_day == datetime(2026, 4, 26)
    assert athlete.target_time == "1:30:00"


@pytest.mark.integration
def test_add_goal_invalid_date_raises_value_error(monkeypatch):
    import titan.core.periodization as periodization_module

    monkeypatch.setattr(periodization_module, "datetime", _FrozenDateTime)
    manager = PeriodizationManager(_AthleteProfileStub())

    with pytest.raises(ValueError):
        manager.add_goal(5.0, "0:20:00", "invalid-date")


@pytest.mark.integration
def test_complete_goal_returns_none_for_missing_or_none_goal_id():
    manager = PeriodizationManager(_AthleteProfileStub())

    assert manager.complete_goal("missing-id", "0:45:00") is None
    assert manager.complete_goal(None, "0:45:00") is None


@pytest.mark.integration
def test_complete_goal_marks_completed_and_creates_suggestions(monkeypatch):
    import titan.core.periodization as periodization_module

    monkeypatch.setattr(periodization_module, "datetime", _FrozenDateTime)
    manager = PeriodizationManager(_AthleteProfileStub())
    goal = manager.add_goal(10.0, "0:45:00", "2026-05-01")

    result = manager.complete_goal(goal["goal_id"], "0:44:00")

    assert result is not None
    completed = result["completed"]
    suggestions = result["suggestions"]

    assert completed["status"] == "COMPLETED"
    assert completed["actual_time"] == "0:44:00"
    assert completed in manager.completed_goals
    assert goal not in manager.goals

    assert suggestions[0]["type"] == "IMPROVE"
    assert suggestions[0]["distance"] == 10.0
    assert suggestions[1]["type"] == "STEP_UP"
    assert suggestions[1]["distance"] == 20.0
