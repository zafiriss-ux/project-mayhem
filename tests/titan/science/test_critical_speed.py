from __future__ import annotations

from datetime import datetime, timedelta

from titan.science.critical_speed import CriticalSpeedEngine, CriticalSpeedTracker


def test_estimate_cs_and_dprime_returns_none_with_insufficient_or_invalid_points() -> None:
    assert CriticalSpeedEngine.estimate_cs_and_dprime([(3000.0, 0.0)]) == (None, None)
    assert CriticalSpeedEngine.estimate_cs_and_dprime([(3000.0, -10.0), (5000.0, 0.0)]) == (None, None)


def test_estimate_cs_and_dprime_returns_none_when_regression_denominator_is_zero() -> None:
    cs, d_prime = CriticalSpeedEngine.estimate_cs_and_dprime([(3000.0, 600.0), (5000.0, 600.0)])

    assert (cs, d_prime) == (None, None)


def test_estimate_cs_and_dprime_fits_linear_distance_time_model() -> None:
    performances = [(2500.0, 600.0), (3300.0, 800.0), (4100.0, 1000.0)]

    cs, d_prime = CriticalSpeedEngine.estimate_cs_and_dprime(performances)

    assert cs == 4.0
    assert d_prime == 100.0


def test_time_to_exhaustion_handles_invalid_or_sustainable_inputs() -> None:
    assert CriticalSpeedEngine.time_to_exhaustion_at_pace(None, 120.0, 240.0) is None
    assert CriticalSpeedEngine.time_to_exhaustion_at_pace(4.0, None, 240.0) is None
    assert CriticalSpeedEngine.time_to_exhaustion_at_pace(4.0, 120.0, 0.0) is None
    assert CriticalSpeedEngine.time_to_exhaustion_at_pace(4.0, 120.0, 250.0) is None


def test_time_to_exhaustion_returns_none_when_d_prime_is_zero_or_negative() -> None:
    assert CriticalSpeedEngine.time_to_exhaustion_at_pace(4.0, 0.0, 200.0) is None
    assert CriticalSpeedEngine.time_to_exhaustion_at_pace(4.0, -50.0, 200.0) is None


def test_time_to_exhaustion_returns_formula_result_for_unsustainable_pace() -> None:
    tte = CriticalSpeedEngine.time_to_exhaustion_at_pace(4.0, 120.0, 200.0)

    assert tte == 120.0


def test_tracker_update_applies_ewma_and_sets_speed_archetype() -> None:
    tracker = CriticalSpeedTracker()

    tracker.update("2026-01-01", 4.0, 1200.0)
    tracker.update("2026-01-02", 5.0, 2000.0)

    assert tracker.cs_smoothed == 4.3
    assert tracker.archetype == "SPEED"


def test_tracker_archetype_guard_falls_back_to_hybrid_when_d_prime_missing_or_zero() -> None:
    tracker = CriticalSpeedTracker()

    tracker.cs_smoothed = 4.0
    tracker.d_prime = 0.0
    tracker._update_archetype()

    assert tracker.archetype == "HYBRID"


def test_tracker_archetype_classifies_endurance_and_hybrid_ratio_bands() -> None:
    tracker = CriticalSpeedTracker()

    tracker.cs_smoothed = 4.0
    tracker.d_prime = 500.0
    tracker._update_archetype()
    assert tracker.archetype == "ENDURANCE"

    tracker.d_prime = 800.0
    tracker._update_archetype()
    assert tracker.archetype == "HYBRID"


def test_tau_multiplier_matches_archetype() -> None:
    tracker = CriticalSpeedTracker()

    tracker.archetype = "SPEED"
    assert tracker.tau_w_prime_multiplier == 1.175

    tracker.archetype = "ENDURANCE"
    assert tracker.tau_w_prime_multiplier == 0.925

    tracker.archetype = "HYBRID"
    assert tracker.tau_w_prime_multiplier == 1.0


def test_confidence_uses_recency_and_sample_count_with_invalid_date_fallback() -> None:
    tracker = CriticalSpeedTracker()
    recent_day = (datetime.now() - timedelta(days=1)).date().isoformat()

    tracker.update(recent_day, 4.0, 600.0)
    assert tracker.confidence > 0.0

    tracker.cs_raw_history.append(("not-a-date", 4.2))
    tracker._update_confidence()
    assert tracker.confidence == 0.2


def test_apply_thermal_returns_none_without_cs_and_applies_rounding_and_floor() -> None:
    tracker = CriticalSpeedTracker()

    assert tracker.apply_thermal(25.0) is None

    tracker.cs_smoothed = 5.0
    assert tracker.apply_thermal(20.0) == 5.0
    assert tracker.apply_thermal(30.0) == 4.75
    assert tracker.apply_thermal(80.0) == 4.25


def test_gap_correct_pace_respects_uphill_downhill_adjustment_and_floor() -> None:
    assert CriticalSpeedTracker.gap_correct_pace(300.0, 2.0) == 280.0
    assert CriticalSpeedTracker.gap_correct_pace(300.0, -2.0) == 310.0
    assert CriticalSpeedTracker.gap_correct_pace(65.0, 2.0) == 60.0
