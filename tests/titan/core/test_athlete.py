from titan.core.athlete import UniversalAthleteProfile


def test_default_profile_construction_is_safe():
    profile = UniversalAthleteProfile()

    assert profile.athlete_id.startswith("ATH_")
    assert profile.name == "Default Athlete"
    assert profile.gender == "M"
    assert profile.age == 43
    assert profile.height_cm == 180
    assert profile.weight_kg == 75.0


def test_set_demographics_zero_weight_keeps_existing_weight_thresholds():
    profile = UniversalAthleteProfile()

    profile.set_demographics(gender="f", age=0, height_cm=0, weight_kg=0)

    assert profile.gender == "F"
    assert profile.age == 0
    assert profile.height_cm == 0
    assert profile.weight_kg == 0
    assert profile.weight_floor == 75.0
    assert profile.weight_ceiling == 76.2
    assert profile.weight_panic == 74.5


def test_set_demographics_negative_weight_updates_thresholds_as_implemented():
    profile = UniversalAthleteProfile()

    profile.set_demographics(gender="m", age=30, height_cm=175.0, weight_kg=-70.0)

    assert profile.weight_floor == -70.5
    assert profile.weight_ceiling == -68.8
    assert profile.weight_panic == -71.5


def test_set_hr_data_derives_max_and_threshold_from_age_when_missing():
    profile = UniversalAthleteProfile()
    profile.age = 40

    profile.set_hr_data(resting_hr=50, max_hr=None)

    assert profile.resting_hr == 50
    assert profile.max_hr == 180
    assert profile.threshold_hr == 158


def test_set_hr_data_zero_max_hr_falls_back_to_age_formula():
    profile = UniversalAthleteProfile()
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
