"""The Docker worker must build a real DailyCoach and reach run_morning_routine.

Before this test the worker was covered only by source-grep tests, and every
morning cycle raised TypeError while constructing collaborators (wrong
constructor keywords), which the cycle's generic except swallowed.
"""

import threading
from datetime import UTC, datetime

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DailyCoach


@pytest.fixture
def worker_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    return DatabaseManager(db_dir=tmp_path)


@pytest.mark.integration
def test_build_daily_coach_returns_wired_coach(worker_db):
    from titan.worker import _build_daily_coach

    coach = _build_daily_coach(worker_db)

    assert isinstance(coach, DailyCoach)
    assert coach.db is worker_db
    assert coach.athlete_id == "owner"
    assert coach.hrv_engine is coach.engines.hrv
    assert coach.weekly_planner.hrv_engine is coach.engines.hrv


@pytest.mark.integration
def test_build_daily_coach_scopes_engines_to_athlete(worker_db):
    from titan.worker import _build_daily_coach

    # Since Phase 4 step 3 an athlete other than the owner needs a stored profile (ADR-0067 D5).
    worker_db.conn.execute(
        "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES ('a-00000002', 'B', 'now')"
    )
    worker_db.save_athlete_profile("a-00000002", {
        "birth_date": "1990-05-01", "sex": "F", "weight_kg": 58.0, "height_cm": 165,
        "max_hr": 186, "threshold_hr": 166, "training_phase": "BASE", "training_goal": "10K",
        "location_city": "Thessaloniki", "location_country": "GR",
    })
    # Since step 4 the athlete also needs their own Garmin account and token (ADR-0067 D9).
    worker_db.bind_garmin_account("a-00000002", "garmin-b")
    worker_db.set_garmin_token_state("a-00000002", "ok")

    coach = _build_daily_coach(worker_db, athlete_id="a-00000002")

    assert coach.athlete_id == "a-00000002"
    assert coach.athlete_profile.athlete_id == "a-00000002"
    assert coach.athlete_profile.max_hr == 186
    assert coach.garmin.athlete_id == "a-00000002"
    assert coach.garmin.token_only is True


@pytest.mark.integration
def test_run_forever_reaches_morning_routine(worker_db, tmp_path, monkeypatch):
    from titan import worker

    stop = threading.Event()
    calls: list[str] = []

    def _fake_routine(self):
        calls.append(self.athlete_id)
        stop.set()

    def _no_cycle_error(*_args, **_kwargs):
        raise AssertionError("worker_cycle_error: coach construction failed")

    monkeypatch.setattr(DailyCoach, "run_morning_routine", _fake_routine)
    monkeypatch.setattr(worker, "_run_backup", lambda db: None)
    monkeypatch.setattr(worker, "_seconds_until_next_run", lambda *a, **k: 0.01)
    # After 07:00 UTC, so today's routine is due whenever the suite runs.
    monkeypatch.setattr(worker, "_utc_now", lambda: datetime(2026, 10, 9, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(worker.logging.getLogger("titan.worker.runner"), "exception", _no_cycle_error)

    worker.run_forever(str(tmp_path / "titan_core.db"), shutdown_event=stop)

    assert calls == ["owner"]


@pytest.mark.integration
@pytest.mark.parametrize("env_max_hr", [None, "177"])
def test_worker_uses_the_console_profile_max_hr(worker_db, monkeypatch, env_max_hr):
    """T5-117: worker and console read max HR from one profile, with one default."""
    from titan.core.athlete import UniversalAthleteProfile
    from titan.worker import _build_daily_coach

    if env_max_hr is None:
        monkeypatch.delenv("ATHLETE_MAX_HR", raising=False)
    else:
        monkeypatch.setenv("ATHLETE_MAX_HR", env_max_hr)

    coach = _build_daily_coach(worker_db)

    expected = UniversalAthleteProfile.from_env().max_hr
    assert coach.athlete_max_hr == expected
    assert expected == (191 if env_max_hr is None else 177)


@pytest.mark.integration
def test_worker_refuses_to_start_on_malformed_max_hr(worker_db, tmp_path, monkeypatch):
    from titan import worker

    monkeypatch.setenv("ATHLETE_MAX_HR", "not-a-number")
    monkeypatch.setattr(worker, "_run_backup", lambda db: pytest.fail("worker ran past start-up"))

    with pytest.raises(SystemExit):
        worker.run_forever(str(tmp_path / "titan_core.db"), shutdown_event=threading.Event())


@pytest.mark.integration
def test_worker_coach_carries_the_profile_object(worker_db, monkeypatch):
    """T5-117 / D-033: the coach holds the profile itself; max HR is read from it once."""
    from titan.core.athlete import UniversalAthleteProfile
    from titan.worker import _build_daily_coach

    monkeypatch.setenv("ATHLETE_MAX_HR", "183")

    coach = _build_daily_coach(worker_db)

    assert isinstance(coach.athlete_profile, UniversalAthleteProfile)
    assert coach.athlete_profile.max_hr == 183
    assert coach.athlete_max_hr == 183
    assert coach.garmin.athlete_max_hr == 183


@pytest.mark.unit
def test_daily_coach_refuses_a_max_hr_that_disagrees_with_the_profile():
    from titan.core.athlete import UniversalAthleteProfile

    profile = UniversalAthleteProfile()
    profile.max_hr = 183

    with pytest.raises(ValueError, match="disagrees"):
        DailyCoach(*([None] * 9), athlete_max_hr=170, athlete_profile=profile)


@pytest.mark.integration
def test_weekly_plan_uses_the_coach_profile(worker_db, monkeypatch):
    """The Sunday plan reads the same profile the coach was built with (D-033)."""
    from titan import worker
    from titan.core.athlete import UniversalAthleteProfile

    seen: list[dict] = []
    coach = worker._build_daily_coach(worker_db)
    monkeypatch.setattr(
        coach.weekly_planner,
        "generate_weekly_plan",
        lambda athlete_profile, phase: seen.append(athlete_profile) or {"week_start": "2026-10-12"},
    )
    monkeypatch.setattr(coach.telegram, "send_weekly_plan", lambda plan: True)
    monkeypatch.setattr(
        UniversalAthleteProfile, "from_env", classmethod(lambda cls: pytest.fail("profile read from env again")),
    )

    worker._generate_weekly_plan(coach, worker_db, "owner")

    assert seen == [coach.athlete_profile.to_dict()]
