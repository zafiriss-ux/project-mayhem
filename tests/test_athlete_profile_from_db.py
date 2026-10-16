"""Phase 4 step 3: each athlete's profile comes from the database (ADR-0067 D5, D7.1; D-092).

- The owner keeps reading .env (from_env), so the owner's mornings do not change.
- Any other athlete reads their athlete_profiles row, with no default anywhere.
- An athlete with no complete profile is not run: nothing is built or called for them,
  and they never receive the owner's values.
"""

from __future__ import annotations

from datetime import date

import pytest

from titan.core.athlete import (
    AthleteNotReady,
    UniversalAthleteProfile,
    load_athlete_profile,
    profile_problems,
)
from titan.core.database import DatabaseManager

_TODAY = date(2026, 10, 16)
_ATHLETE = "a-0000c0de"
_RECORD = {
    "birth_date": "1992-03-14",
    "sex": "F",
    "weight_kg": 61.5,
    "height_cm": 168.0,
    "max_hr": 184,
    "threshold_hr": 165,
    "training_phase": "build",
    "training_goal": "hm",
    "location_city": "Patras",
    "location_country": "GR",
}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    manager = DatabaseManager(db_dir=tmp_path)
    manager.conn.execute(
        "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, 'Eleni', 'now')",
        (_ATHLETE,),
    )
    manager.conn.commit()
    yield manager
    manager.close()


@pytest.mark.unit
def test_the_owner_still_reads_env(db, monkeypatch) -> None:
    monkeypatch.setenv("ATHLETE_MAX_HR", "177")
    profile = load_athlete_profile(db, "owner", today=_TODAY)
    assert profile.max_hr == 177
    assert db.get_athlete_profile("owner") is None


@pytest.mark.unit
def test_the_owner_profile_is_never_stored(db) -> None:
    with pytest.raises(ValueError, match=".env"):
        db.save_athlete_profile("owner", dict(_RECORD))


@pytest.mark.unit
def test_an_athlete_gets_only_their_stored_values(db, monkeypatch) -> None:
    monkeypatch.setenv("ATHLETE_MAX_HR", "199")
    db.save_athlete_profile(_ATHLETE, dict(_RECORD))

    profile = load_athlete_profile(db, _ATHLETE, today=_TODAY)

    assert profile.athlete_id == _ATHLETE
    assert profile.name == "Eleni"
    assert profile.age == 34
    assert profile.gender == "F"
    assert (profile.weight_kg, profile.height_cm) == (61.5, 168.0)
    assert (profile.max_hr, profile.threshold_hr) == (184, 165)
    assert (profile.training_phase, profile.current_goal) == ("BUILD", "HM")
    assert (profile.location_city, profile.location_country) == ("Patras", "GR")
    assert profile.to_context()["max_hr"] == 184


@pytest.mark.unit
def test_an_athlete_never_receives_the_owners_constructor_values(db) -> None:
    db.save_athlete_profile(_ATHLETE, dict(_RECORD))
    profile = load_athlete_profile(db, _ATHLETE, today=_TODAY)
    owner_defaults = UniversalAthleteProfile(athlete_id="owner")

    for field in ("resting_hr", "vo2_max", "race_day", "base_5k_sec", "critical_speed_m_per_s", "d_prime_m"):
        assert getattr(profile, field) is None, field
        assert getattr(owner_defaults, field) is not None, field
    assert profile.paces == {}


@pytest.mark.unit
def test_an_athlete_without_a_profile_is_not_ready(db) -> None:
    with pytest.raises(AthleteNotReady) as caught:
        load_athlete_profile(db, _ATHLETE, today=_TODAY)
    assert caught.value.reason == "no profile"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value", "problem"),
    [
        ("max_hr", None, "max_hr: missing"),
        ("location_city", "", "location_city: missing"),
        ("birth_date", "2010-01-01", "birth_date: under 18"),
        ("birth_date", "14/03/1992", "birth_date: not an ISO date"),
        ("sex", "X", "sex: must be M or F"),
        ("max_hr", 240, "max_hr: must be between 100 and 220"),
        ("weight_kg", "heavy", "weight_kg: not a number"),
        ("training_phase", "RACE", "training_phase: unknown"),
        ("training_goal", "50K", "training_goal: unknown"),
    ],
)
def test_an_incomplete_or_out_of_range_profile_is_refused(field, value, problem) -> None:
    record = {**_RECORD, field: value}
    assert problem in profile_problems(record, _TODAY)
    with pytest.raises(AthleteNotReady, match=problem):
        UniversalAthleteProfile.from_record(_ATHLETE, "Eleni", record, today=_TODAY)


@pytest.mark.unit
def test_save_refuses_a_profile_that_could_not_be_used(db) -> None:
    with pytest.raises(ValueError, match="under 18"):
        db.save_athlete_profile(_ATHLETE, {**_RECORD, "birth_date": "2012-06-01"})
    assert db.get_athlete_profile(_ATHLETE) is None


@pytest.mark.unit
def test_a_bad_row_written_past_save_is_refused_on_load(db) -> None:
    db.save_athlete_profile(_ATHLETE, dict(_RECORD))
    db.conn.execute("UPDATE athlete_profiles SET max_hr = 40 WHERE athlete_id = ?", (_ATHLETE,))
    db.conn.commit()
    with pytest.raises(AthleteNotReady, match="max_hr"):
        load_athlete_profile(db, _ATHLETE, today=_TODAY)


@pytest.mark.unit
def test_saving_again_updates_the_profile(db) -> None:
    db.save_athlete_profile(_ATHLETE, dict(_RECORD))
    db.save_athlete_profile(_ATHLETE, {**_RECORD, "weight_kg": 60.0, "training_phase": "PEAK"})
    _name, stored = db.get_athlete_profile(_ATHLETE)
    assert (stored["weight_kg"], stored["training_phase"]) == (60.0, "PEAK")
    assert db.conn.execute("SELECT COUNT(*) FROM athlete_profiles").fetchone()[0] == 1


@pytest.mark.integration
def test_the_morning_of_an_athlete_without_a_profile_builds_and_calls_nothing(db, monkeypatch) -> None:
    from titan import worker
    from titan.integrations import garmin_sync, telegram_bot, weather_api
    from titan.orchestration import engine_registry

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("built a collaborator for an athlete who is not ready")

    monkeypatch.setattr(garmin_sync, "GarminSync", _forbidden)
    monkeypatch.setattr(weather_api, "WeatherAPI", _forbidden)
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _forbidden)
    monkeypatch.setattr(engine_registry.EngineRegistry, "from_db", _forbidden)

    with pytest.raises(AthleteNotReady):
        worker._run_morning(db, _ATHLETE)
    assert db.conn.execute("SELECT COUNT(*) FROM weekly_plans").fetchone()[0] == 0


@pytest.mark.integration
def test_the_weekly_plan_of_another_athlete_never_uses_the_owners_env(db, monkeypatch) -> None:
    from titan import worker

    class _CoachWithoutProfile:
        athlete_profile = None

    with pytest.raises(AthleteNotReady):
        worker._generate_weekly_plan(_CoachWithoutProfile(), db, _ATHLETE)
