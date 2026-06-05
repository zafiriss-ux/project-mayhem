"""T5-119 — Profile editor: _save_athlete_profile_to_env + validation contract."""

import pytest

from titan.ui.menu_system import (
    VALID_TRAINING_GOALS,
    VALID_TRAINING_PHASES,
    _read_current_profile,
    _validate_field,
)
from titan.ui.setup_wizard import _save_athlete_profile_to_env

# ── _save_athlete_profile_to_env ─────────────────────────────────────────────

@pytest.mark.unit
def test_save_athlete_profile_updates_existing_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GARMIN_EMAIL=foo@bar.com\nATHLETE_MAX_HR=185\n")
    monkeypatch.setattr("titan.ui.setup_wizard.ENV_PATH", env_file)

    _save_athlete_profile_to_env({"ATHLETE_MAX_HR": "160"})

    content = env_file.read_text()
    assert "ATHLETE_MAX_HR=160" in content
    assert "ATHLETE_MAX_HR=185" not in content


@pytest.mark.unit
def test_save_athlete_profile_appends_missing_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GARMIN_EMAIL=foo@bar.com\n")
    monkeypatch.setattr("titan.ui.setup_wizard.ENV_PATH", env_file)

    _save_athlete_profile_to_env({"ATHLETE_AGE": "47"})

    content = env_file.read_text()
    assert "ATHLETE_AGE=47" in content


@pytest.mark.unit
def test_save_athlete_profile_preserves_other_keys(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GARMIN_EMAIL=foo@bar.com\nATHLETE_MAX_HR=185\n")
    monkeypatch.setattr("titan.ui.setup_wizard.ENV_PATH", env_file)

    _save_athlete_profile_to_env({"ATHLETE_MAX_HR": "160"})

    content = env_file.read_text()
    assert "GARMIN_EMAIL=foo@bar.com" in content


# ── Validation contract ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_phase_choices_are_valid():
    for phase in ("BASE", "BUILD", "PEAK", "TAPER"):
        ok, _ = _validate_field("TRAINING_PHASE", phase)
        assert ok, f"Expected {phase!r} to be valid"
    assert frozenset({"BASE", "BUILD", "PEAK", "TAPER"}) == VALID_TRAINING_PHASES


@pytest.mark.unit
def test_goal_choices_are_valid():
    for goal in ("5K", "10K", "HM", "M"):
        ok, _ = _validate_field("TRAINING_GOAL", goal)
        assert ok, f"Expected {goal!r} to be valid"
    assert frozenset({"5K", "10K", "HM", "M"}) == VALID_TRAINING_GOALS


@pytest.mark.unit
def test_invalid_max_hr_rejected():
    too_low_ok, _ = _validate_field("ATHLETE_MAX_HR", "50")
    assert not too_low_ok, "50 bpm should be rejected (below range 100-220)"

    too_high_ok, _ = _validate_field("ATHLETE_MAX_HR", "300")
    assert not too_high_ok, "300 bpm should be rejected (above range 100-220)"

    valid_ok, _ = _validate_field("ATHLETE_MAX_HR", "160")
    assert valid_ok, "160 bpm should be accepted"


# ── Case-insensitive normalisation ───────────────────────────────────────────

@pytest.mark.unit
def test_goal_case_insensitive(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GARMIN_EMAIL=foo@bar.com\n")
    monkeypatch.setattr("titan.ui.setup_wizard.ENV_PATH", env_file)

    _save_athlete_profile_to_env({"TRAINING_GOAL": "10k"})

    content = env_file.read_text()
    assert "TRAINING_GOAL=10K" in content


@pytest.mark.unit
def test_phase_case_insensitive(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GARMIN_EMAIL=foo@bar.com\n")
    monkeypatch.setattr("titan.ui.setup_wizard.ENV_PATH", env_file)

    _save_athlete_profile_to_env({"TRAINING_PHASE": "build"})

    content = env_file.read_text()
    assert "TRAINING_PHASE=BUILD" in content


@pytest.mark.unit
def test_display_reads_from_env_not_object(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ATHLETE_NAME=OldName\n")
    monkeypatch.setattr("titan.ui.setup_wizard.ENV_PATH", env_file)

    _save_athlete_profile_to_env({"ATHLETE_NAME": "TestAthlete"})
    profile = _read_current_profile()

    assert profile["name"] == "TestAthlete"
