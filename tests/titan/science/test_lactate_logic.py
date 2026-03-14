from titan.science.lactate_logic import LactateLogic


def test_estimate_lt1_happy_path_in_lt1_zone():
    result = LactateLogic.estimate_lt1(hr_percent_max=70.0, drift_percent=2.5)

    assert result["is_lt1"] is True


def test_estimate_lt1_uses_threshold_source_of_truth(monkeypatch):
    import titan.science.lactate_logic as lactate_logic

    monkeypatch.setattr(lactate_logic, "LACTATE_LT1_MAX_DRIFT_PCT", 2.0)
    monkeypatch.setattr(lactate_logic, "LACTATE_LT1_MAX_HR_PCT", 75.0)

    at_threshold = LactateLogic.estimate_lt1(hr_percent_max=75.0, drift_percent=1.9)
    drift_boundary = LactateLogic.estimate_lt1(hr_percent_max=75.0, drift_percent=2.0)

    assert at_threshold["is_lt1"] is True
    assert drift_boundary["is_lt1"] is False


def test_estimate_lt2_happy_path_in_threshold_zone():
    result = LactateLogic.estimate_lt2(hr_stable=True, rpe=6.5)

    assert result["is_lt2"] is True


def test_estimate_lt2_uses_threshold_source_of_truth(monkeypatch):
    import titan.science.lactate_logic as lactate_logic

    monkeypatch.setattr(lactate_logic, "LACTATE_LT2_MIN_RPE", 6.2)
    monkeypatch.setattr(lactate_logic, "LACTATE_LT2_MAX_RPE", 6.8)

    below_min = LactateLogic.estimate_lt2(hr_stable=True, rpe=6.1)
    at_min = LactateLogic.estimate_lt2(hr_stable=True, rpe=6.2)
    above_max = LactateLogic.estimate_lt2(hr_stable=True, rpe=6.9)

    assert below_min["is_lt2"] is False
    assert at_min["is_lt2"] is True
    assert above_max["is_lt2"] is False
