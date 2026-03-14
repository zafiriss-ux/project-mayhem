from datetime import datetime

from titan.core.athlete import UniversalAthleteProfile


def test_default_profile_construction_is_safe(athlete_profile_factory):
    profile = athlete_profile_factory()

    assert profile.athlete_id.startswith("ATH_")
    assert profile.name == "Default Athlete"
    assert profile.gender == "M"
    assert profile.age == 43
    assert profile.height_cm == 180
    assert profile.weight_kg == 75.0


def test_set_demographics_zero_weight_keeps_existing_weight_thresholds(athlete_profile_factory):
    profile = athlete_profile_factory()

    profile.set_demographics(gender="f", age=0, height_cm=0, weight_kg=0)

    assert profile.gender == "F"
    assert profile.age == 0
    assert profile.height_cm == 0
    assert profile.weight_kg == 0
    assert profile.weight_floor == 75.0
    assert profile.weight_ceiling == 76.2
    assert profile.weight_panic == 74.5


def test_set_demographics_negative_weight_updates_thresholds_as_implemented(athlete_profile_factory):
    profile = athlete_profile_factory()

    profile.set_demographics(gender="m", age=30, height_cm=175.0, weight_kg=-70.0)

    assert profile.weight_floor == -70.5
    assert profile.weight_ceiling == -68.8
    assert profile.weight_panic == -71.5


def test_set_hr_data_derives_max_and_threshold_from_age_when_missing(athlete_profile_factory):
    profile = athlete_profile_factory()
    profile.age = 40

    profile.set_hr_data(resting_hr=50, max_hr=None)

    assert profile.resting_hr == 50
    assert profile.max_hr == 180
    assert profile.threshold_hr == 158


def test_set_hr_data_zero_max_hr_falls_back_to_age_formula(athlete_profile_factory):
    profile = athlete_profile_factory()
    profile.age = 41

    profile.set_hr_data(resting_hr=48, max_hr=0)

    assert profile.max_hr == 179
    assert profile.threshold_hr == 157


def test_time_conversion_helpers_handle_normal_and_invalid_inputs():
    assert UniversalAthleteProfile.str_to_sec("12:34") == 754
    assert UniversalAthleteProfile.str_to_sec("1:02:03") == 3723
    assert UniversalAthleteProfile.str_to_sec("bad-input") == 0
    assert UniversalAthleteProfile.sec_to_str(754) == "12:34"


def test_from_dict_is_deterministic_for_identical_inputs():
    data = {
        "athlete_id": "ATH_FIXED",
        "name": "Runner",
        "gender": "F",
        "age": 35,
        "height_cm": 167.5,
        "weight_kg": 59.2,
        "resting_hr": 47,
        "max_hr": 186,
        "threshold_hr": 163,
        "vo2_max": 60.0,
        "race_day": "2026-06-01T00:00:00",
        "current_goal": "10k",
        "target_time": "38:00",
        "personal_bests": {"5k": "18:30"},
        "weight_floor": 58.8,
        "paces": {"EASY": "5:00"},
    }

    profile_a = UniversalAthleteProfile.from_dict(data)
    profile_b = UniversalAthleteProfile.from_dict(data)

    assert profile_a.to_dict() == profile_b.to_dict()


def test_to_dict_and_from_dict_round_trip_preserves_weight_guardrails(athlete_profile_factory):
    profile = athlete_profile_factory()
    profile.weight_floor = 63.1
    profile.weight_ceiling = 64.3
    profile.weight_panic = 62.4

    round_tripped = UniversalAthleteProfile.from_dict(profile.to_dict())

    assert round_tripped.weight_floor == 63.1
    assert round_tripped.weight_ceiling == 64.3
    assert round_tripped.weight_panic == 62.4


def test_to_dict_includes_weight_guardrail_fields(athlete_profile_factory):
    profile = athlete_profile_factory()

    data = profile.to_dict()

    assert "weight_ceiling" in data
    assert "weight_panic" in data


def test_from_dict_missing_weight_guardrail_fields_keeps_constructor_defaults():
    profile = UniversalAthleteProfile.from_dict({"name": "Runner"})

    assert profile.weight_floor == 75.0
    assert profile.weight_ceiling == 76.2
    assert profile.weight_panic == 74.5


def test_generated_athlete_ids_are_unique_when_created_in_same_second(monkeypatch):
    fixed_now = datetime(2026, 3, 14, 9, 30, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr("titan.core.athlete.datetime", FixedDateTime)

    profile_a = UniversalAthleteProfile()
    profile_b = UniversalAthleteProfile()

    assert profile_a.athlete_id != profile_b.athlete_id


def test_generated_athlete_ids_include_timestamp_prefix_and_unique_suffix(monkeypatch):
    fixed_now = datetime(2026, 3, 14, 9, 30, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr("titan.core.athlete.datetime", FixedDateTime)

    profile_a = UniversalAthleteProfile()
    profile_b = UniversalAthleteProfile()
    expected_prefix = "ATH_20260314093000_"

    assert profile_a.athlete_id.startswith(expected_prefix)
    assert profile_b.athlete_id.startswith(expected_prefix)
    assert profile_a.athlete_id.split("_", maxsplit=2)[2] != profile_b.athlete_id.split("_", maxsplit=2)[2]
