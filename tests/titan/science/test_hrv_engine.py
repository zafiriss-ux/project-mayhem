import math

from titan.science.hrv_engine import HRVGuidedEngine


def _build_engine_with_history(values: list[float], baseline_days: int = 7) -> HRVGuidedEngine:
    engine = HRVGuidedEngine(baseline_days=baseline_days)
    for index, value in enumerate(values):
        engine.add_hrv_measurement(f"2026-01-{index + 1:02d}", value)
    return engine


def test_empty_state_returns_safe_defaults_without_crashing() -> None:
    engine = HRVGuidedEngine()

    summary = engine.get_hrv_summary()
    recommendation = engine.get_training_recommendation(today_hrv=50.0, planned_session="TEMPO")

    assert summary == {
        "latest_hrv": 0.0,
        "baseline": 0.0,
        "std_dev": 0.0,
        "trend": "Need 14+ days for trend analysis",
        "data_points": 0,
    }
    assert recommendation == (
        "TEMPO",
        "Insufficient HRV data - proceed with plan",
        "LOW",
    )


def test_identical_inputs_produce_identical_outputs() -> None:
    values = [45.0, 47.0, 46.0, 44.0, 48.0, 46.0, 45.0, 47.0]
    engine_a = _build_engine_with_history(values)
    engine_b = _build_engine_with_history(values)

    assert engine_a.get_hrv_summary() == engine_b.get_hrv_summary()
    assert engine_a.calculate_baseline() == engine_b.calculate_baseline()
    assert engine_a.calculate_ln_rmssd_deviation() == engine_b.calculate_ln_rmssd_deviation()
    assert engine_a.get_training_recommendation(46.0, "INTERVALS") == engine_b.get_training_recommendation(
        46.0, "INTERVALS"
    )


def test_numeric_outputs_are_finite_and_deviation_is_bounded() -> None:
    engine = _build_engine_with_history([40.0, 42.0, 39.0, 41.0, 43.0, 40.0, 42.0])

    summary = engine.get_hrv_summary()
    deviation = engine.calculate_ln_rmssd_deviation()

    assert math.isfinite(summary["latest_hrv"])
    assert math.isfinite(summary["baseline"])
    assert math.isfinite(summary["std_dev"])
    assert math.isfinite(deviation)
    assert -1.0 <= deviation <= 1.0


def test_summary_and_recommendation_stay_within_current_expected_ranges() -> None:
    engine = _build_engine_with_history([42.0, 44.0, 46.0, 48.0, 50.0, 52.0, 54.0])

    summary = engine.get_hrv_summary()
    action, reason, confidence = engine.get_training_recommendation(today_hrv=49.0, planned_session="TEMPO")

    assert 0.0 <= summary["latest_hrv"] <= 200.0
    assert 0.0 <= summary["baseline"] <= 200.0
    assert 0.0 <= summary["std_dev"] <= 200.0
    assert action in {"REST", "EASY", "TEMPO", "INTERVALS", "PROGRESSIVE", "HAMMER"}
    assert confidence in {"LOW", "MEDIUM", "HIGH"}
    assert isinstance(reason, str) and reason


def test_low_and_high_hrv_follow_existing_downgrade_and_proceed_behavior() -> None:
    values = [50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 40.0]
    engine = _build_engine_with_history(values)

    low_action, _, low_confidence = engine.get_training_recommendation(today_hrv=45.0, planned_session="INTERVALS")
    high_action, _, high_confidence = engine.get_training_recommendation(today_hrv=55.0, planned_session="INTERVALS")

    assert low_action == "EASY"
    assert low_confidence == "HIGH"
    assert high_action == "INTERVALS"
    assert high_confidence == "HIGH"


def test_minimal_data_points_behavior_is_stable() -> None:
    engine = HRVGuidedEngine()
    engine.add_hrv_measurement("2026-01-01", 50.0)

    assert engine.calculate_baseline() == (None, None)
    assert engine.get_training_recommendation(49.0, "EASY") == (
        "EASY",
        "Insufficient HRV data - proceed with plan",
        "LOW",
    )
    assert engine.calculate_rmssd_from_rr_intervals([1000.0]) is None
    assert engine.calculate_rmssd_from_rr_intervals([1000.0, 1020.0]) == 20.0
