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


# ── T5-55: ESI-aware thermal degradation ─────────────────────────────────────


def test_apply_thermal_with_dew_point_none_falls_back_to_dry_bulb() -> None:
    """T5-55: dew_point_c=None must reproduce the original dry-bulb behaviour."""
    tracker = CriticalSpeedTracker()
    tracker.cs_smoothed = 5.0

    assert tracker.apply_thermal(20.0, dew_point_c=None) == 5.0
    assert tracker.apply_thermal(30.0, dew_point_c=None) == 4.75
    assert tracker.apply_thermal(80.0, dew_point_c=None) == 4.25


def test_apply_thermal_esi_below_moderate_threshold_no_degradation() -> None:
    """T5-55: ESI < ESI_MODERATE_MIN (16) → factor = 1.0, no degradation."""
    tracker = CriticalSpeedTracker()
    tracker.cs_smoothed = 4.0

    # temp=10, dew=10 → ESI = 10 + 0.5*10 = 15 < 16
    result = tracker.apply_thermal(10.0, dew_point_c=10.0)

    assert result == 4.0


def test_apply_thermal_esi_at_moderate_threshold_no_degradation() -> None:
    """T5-55: ESI == ESI_MODERATE_MIN (16) → no degradation (boundary)."""
    tracker = CriticalSpeedTracker()
    tracker.cs_smoothed = 4.0

    # temp=12, dew=8 → ESI = 12 + 0.5*8 = 16
    result = tracker.apply_thermal(12.0, dew_point_c=8.0)

    assert result == 4.0


def test_apply_thermal_esi_above_moderate_threshold_degrades_cs() -> None:
    """T5-55: ESI > 16 → CS is reduced; higher ESI → greater reduction."""
    tracker = CriticalSpeedTracker()
    tracker.cs_smoothed = 4.0

    # ESI = 21 → excess_bands = (21-16)/5 = 1.0 → factor = 0.975
    result_moderate = tracker.apply_thermal(15.0, dew_point_c=12.0)  # ESI=15+6=21
    assert result_moderate == round(4.0 * 0.975, 3)

    # ESI = 26 → excess_bands = (26-16)/5 = 2.0 → factor = 0.95
    result_high = tracker.apply_thermal(20.0, dew_point_c=12.0)  # ESI=20+6=26
    assert result_high == round(4.0 * 0.95, 3)


def test_apply_thermal_esi_extreme_is_floored_at_85_pct() -> None:
    """T5-55: ESI high enough to reach the 85% floor."""
    tracker = CriticalSpeedTracker()
    tracker.cs_smoothed = 4.0

    # ESI = 16 + 20*5 / 5 would be 116, well past floor
    # ESI = 56 → excess_bands = (56-16)/5 = 8 → 1 - 0.025*8 = 0.8 → floor 0.85
    result = tracker.apply_thermal(50.0, dew_point_c=12.0)  # ESI=50+6=56

    assert result == round(4.0 * 0.85, 3)


def test_apply_thermal_esi_returns_none_without_cs_smoothed() -> None:
    """T5-55: returns None when cs_smoothed is None, even with dew_point_c provided."""
    tracker = CriticalSpeedTracker()

    assert tracker.apply_thermal(30.0, dew_point_c=18.0) is None


def test_apply_thermal_esi_higher_than_dry_bulb_for_same_temperature() -> None:
    """T5-55: with dew_point_c provided, humidity increases effective stress vs dry-bulb."""
    tracker = CriticalSpeedTracker()
    tracker.cs_smoothed = 5.0

    # dry-bulb at 22°C: excess = (22-20)/5 = 0.4 → factor = 1 - 0.025*0.4 = 0.99 → 4.95
    dry_result = tracker.apply_thermal(22.0, dew_point_c=None)
    # ESI at 22°C + 18°C dew: ESI = 22 + 9 = 31 → excess=(31-16)/5=3 → factor=1-0.075=0.925
    esi_result = tracker.apply_thermal(22.0, dew_point_c=18.0)

    assert esi_result is not None
    assert dry_result is not None
    assert esi_result < dry_result
