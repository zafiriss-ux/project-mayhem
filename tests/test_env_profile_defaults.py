"""OW-L3 (D-125): a missing ATHLETE_MAX_HR, ATHLETE_THRESHOLD_HR or TRAINING_PHASE is not silent.

``UniversalAthleteProfile.from_env`` still starts with the constructor default, but logs a
WARNING naming the variable, because max HR sets the TRIMP zones and with them load, TSB,
ACWR and H4. The log names the variable only, never a value. Synthetic environment only.
"""

import logging

import pytest

from titan.core.athlete import UniversalAthleteProfile

_WATCHED = ("ATHLETE_MAX_HR", "ATHLETE_THRESHOLD_HR", "TRAINING_PHASE")


def _defaults_used(caplog):
    return [r for r in caplog.records if r.getMessage() == "startup_env_default_used"]


@pytest.mark.parametrize("missing", _WATCHED)
def test_a_missing_physiology_variable_is_warned_about(monkeypatch, caplog, missing):
    values = {"ATHLETE_MAX_HR": "185", "ATHLETE_THRESHOLD_HR": "165", "TRAINING_PHASE": "BASE"}
    for var, value in values.items():
        monkeypatch.setenv(var, value)
    monkeypatch.delenv(missing)
    with caplog.at_level(logging.WARNING, logger="titan"):
        UniversalAthleteProfile.from_env()
    warned = _defaults_used(caplog)
    assert [r.var for r in warned] == [missing]
    assert warned[0].levelno == logging.WARNING
    assert not hasattr(warned[0], "default")  # the variable only, never a value


def test_a_complete_environment_warns_about_nothing(monkeypatch, caplog):
    monkeypatch.setenv("ATHLETE_MAX_HR", "185")
    monkeypatch.setenv("ATHLETE_THRESHOLD_HR", "165")
    monkeypatch.setenv("TRAINING_PHASE", "BASE")
    with caplog.at_level(logging.WARNING, logger="titan"):
        profile = UniversalAthleteProfile.from_env()
    assert _defaults_used(caplog) == []
    assert (profile.max_hr, profile.threshold_hr, profile.training_phase) == (185, 165, "BASE")


def test_the_defaults_still_apply_so_the_owner_still_starts(monkeypatch):
    for var in _WATCHED:
        monkeypatch.delenv(var, raising=False)
    defaults = UniversalAthleteProfile()
    profile = UniversalAthleteProfile.from_env()
    assert (profile.max_hr, profile.threshold_hr, profile.training_phase) == (
        defaults.max_hr, defaults.threshold_hr, "BUILD")


@pytest.mark.parametrize("var", ["ATHLETE_MAX_HR", "ATHLETE_THRESHOLD_HR"])
def test_a_blank_heart_rate_still_refuses_to_start(monkeypatch, var):
    # Unchanged and stricter than a default: a set but unreadable HR stops the start.
    monkeypatch.setenv(var, "  ")
    with pytest.raises(SystemExit):
        UniversalAthleteProfile.from_env()
