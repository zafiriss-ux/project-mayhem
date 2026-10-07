"""T5-117: Verify UniversalAthleteProfile.from_env() unifies the two profile paths."""

import dataclasses
import os

import pytest

from titan.core.athlete import UniversalAthleteProfile


class TestFromEnvUsesEnvVars:
    @pytest.mark.unit
    def test_from_env_uses_env_vars(self, monkeypatch):
        monkeypatch.setenv("ATHLETE_MAX_HR", "160")
        monkeypatch.setenv("ATHLETE_AGE", "47")
        profile = UniversalAthleteProfile.from_env()
        assert profile.max_hr == 160
        assert profile.age == 47


class TestFromEnvSafeDefaults:
    @pytest.mark.unit
    def test_from_env_safe_defaults_when_vars_absent(self, monkeypatch):
        for var in (
            "ATHLETE_NAME", "ATHLETE_AGE", "ATHLETE_WEIGHT",
            "ATHLETE_HEIGHT", "ATHLETE_MAX_HR", "ATHLETE_THRESHOLD_HR",
            "TRAINING_PHASE", "TRAINING_GOAL",
        ):
            monkeypatch.delenv(var, raising=False)
        profile = UniversalAthleteProfile.from_env()
        assert profile.max_hr > 0
        assert profile.age > 0
        assert profile.weight_kg > 0


class TestFromEnvTrainingPhase:
    @pytest.mark.unit
    def test_from_env_training_phase(self, monkeypatch):
        monkeypatch.setenv("TRAINING_PHASE", "PEAK")
        profile = UniversalAthleteProfile.from_env()
        assert profile.training_phase == "PEAK"


class TestProfileToDictRoundTrip:
    @pytest.mark.unit
    def test_profile_to_dict_round_trip(self, monkeypatch):
        monkeypatch.delenv("ATHLETE_MAX_HR", raising=False)
        profile = UniversalAthleteProfile.from_env()
        d = profile.to_dict()
        assert "max_hr" in d or "max_heart_rate" in d


class TestNoDuplicateProfileDictInTitanContext:
    @pytest.mark.unit
    def test_no_duplicate_profile_dict_in_titan_context(self):
        import typing

        from titan.orchestration.contracts import TitanContext
        hints = typing.get_type_hints(TitanContext)
        athlete_fields = [k for k in hints if "athlete" in k.lower()]
        assert len(athlete_fields) == 1


class TestContextProfileDerivedFromUniversalProfile:
    @pytest.mark.unit
    def test_to_context_matches_the_athlete_profile_contract(self, monkeypatch):
        import typing

        from titan.orchestration.contracts import AthleteProfile

        monkeypatch.setenv("ATHLETE_MAX_HR", "177")
        monkeypatch.setenv("TRAINING_PHASE", "PEAK")
        profile = UniversalAthleteProfile.from_env()
        ctx = profile.to_context()
        assert set(ctx) == set(typing.get_type_hints(AthleteProfile))
        assert ctx["max_hr"] == 177
        assert ctx["phase"] == "PEAK"

