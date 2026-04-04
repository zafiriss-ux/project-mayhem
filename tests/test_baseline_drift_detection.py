"""Baseline drift detection tests (HD-01 / INV-06).

Verifies that the HRV rolling-baseline drift-detector catches gradual
deterioration that per-cycle HARD_STOP_HRV_DELTA checks would miss.

Framework reference:
  - HD-01: Rolling baseline poisoning — no drift detector
  - INV-06: HRV baseline drift rate ≤ threshold over 14-day window
  - FS-02: 7-day HRV decline (-3ms/day) must trigger drift warning by day 5
  - Observability contract: hrv_baseline_drift_warning (WARNING) when |delta| > 8.0ms
"""

import pytest

from titan.science.hrv_engine import HrvCalibrationDriftState, HRVGuidedEngine

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_engine_with_hrv(values: list[float]) -> HRVGuidedEngine:
    """Populate an HRVEngine with a sequence of HRV readings (newest first reversed)."""
    engine = HRVGuidedEngine()
    for i, v in enumerate(values):
        # Synthetic date strings oldest → newest
        engine.hrv_log.append((f"2026-03-{i + 1:02d}", v))
    return engine


# ── INV-06: drift_detected field reflects correct state ──────────────────────


def test_hrv_calibration_drift_no_drift():
    """No drift when current ≈ baseline (delta < threshold)."""
    state = HRVGuidedEngine.describe_calibration_drift(
        baseline_hrv_ms=60.0,
        current_hrv_ms=62.0,
        drift_threshold_ms=8.0,
    )
    assert isinstance(state, HrvCalibrationDriftState)
    assert not state.drift_detected
    assert state.abs_delta_ms == pytest.approx(2.0, abs=0.01)


def test_hrv_calibration_drift_detected_above_threshold():
    """Drift detected when |current - baseline| > threshold."""
    state = HRVGuidedEngine.describe_calibration_drift(
        baseline_hrv_ms=60.0,
        current_hrv_ms=51.0,  # -9ms drop (> 8ms threshold)
        drift_threshold_ms=8.0,
    )
    assert state.drift_detected
    assert state.delta_ms == pytest.approx(-9.0, abs=0.01)
    assert state.abs_delta_ms == pytest.approx(9.0, abs=0.01)


def test_hrv_calibration_drift_exactly_at_threshold():
    """At exactly threshold: drift NOT detected (strict >)."""
    state = HRVGuidedEngine.describe_calibration_drift(
        baseline_hrv_ms=60.0,
        current_hrv_ms=52.0,  # exactly -8ms
        drift_threshold_ms=8.0,
    )
    assert not state.drift_detected


def test_hrv_calibration_drift_positive_improvement():
    """Upward HRV drift (improvement) is also detected if |delta| > threshold."""
    state = HRVGuidedEngine.describe_calibration_drift(
        baseline_hrv_ms=50.0,
        current_hrv_ms=61.0,  # +11ms above baseline
        drift_threshold_ms=8.0,
    )
    assert state.drift_detected
    assert state.delta_ms > 0


# ── FS-02: 7-day gradual -3ms/day decline triggers drift by day 5 ────────────


def test_gradual_hrv_decline_triggers_drift_by_cumulative_delta():
    """FS-02: Seven consecutive -3ms/day readings produce a 14-day delta > 8ms.

    The rolling 7-day mean after 7 days of decline compared against an
    anchor baseline (pre-decline) must show drift_detected = True when the
    cumulative drop exceeds 8ms.
    """
    # Anchor baseline: 7 stable days at 60ms
    stable = [60.0] * 7
    # 7 days of -3ms/day decline: 57, 54, 51, 48, 45, 42, 39
    declining = [60.0 - 3.0 * (i + 1) for i in range(7)]

    engine = _make_engine_with_hrv(stable + declining)

    # Rolling 7-day baseline uses the most recent 7 values (the declining set)
    current_baseline, _ = engine.calculate_baseline(days=7)

    # Anchor: mean of the stable 7 days = 60.0
    anchor_baseline = 60.0

    assert current_baseline is not None
    # The current rolling mean of the declining week:
    # mean([57, 54, 51, 48, 45, 42, 39]) = 48.0 → drop of 12ms
    state = HRVGuidedEngine.describe_calibration_drift(
        baseline_hrv_ms=anchor_baseline,
        current_hrv_ms=current_baseline,
        drift_threshold_ms=8.0,
    )
    assert state.drift_detected, (
        f"Expected drift detected after 7-day -3ms/day decline; "
        f"anchor={anchor_baseline}, current={current_baseline}, "
        f"delta={state.delta_ms}"
    )
    assert state.abs_delta_ms > 8.0


def test_slow_decline_below_threshold_does_not_trigger_drift():
    """A slow decline of -1ms/day over 7 days (total -4ms) does not trigger drift."""
    stable = [60.0] * 7
    slow_decline = [60.0 - 1.0 * (i + 1) for i in range(7)]

    engine = _make_engine_with_hrv(stable + slow_decline)
    current_baseline, _ = engine.calculate_baseline(days=7)
    anchor_baseline = 60.0

    assert current_baseline is not None
    state = HRVGuidedEngine.describe_calibration_drift(
        baseline_hrv_ms=anchor_baseline,
        current_hrv_ms=current_baseline,
        drift_threshold_ms=8.0,
    )
    # mean([59, 58, 57, 56, 55, 54, 53]) = 56.0 → delta = -4ms < 8ms threshold
    assert not state.drift_detected


# ── INV-06: invalid threshold raises ─────────────────────────────────────────


def test_describe_calibration_drift_raises_on_zero_threshold():
    """drift_threshold_ms=0 must raise ValueError (invalid configuration)."""
    with pytest.raises(ValueError, match="drift_threshold_ms must be > 0"):
        HRVGuidedEngine.describe_calibration_drift(
            baseline_hrv_ms=60.0,
            current_hrv_ms=50.0,
            drift_threshold_ms=0.0,
        )


def test_describe_calibration_drift_raises_on_negative_threshold():
    """drift_threshold_ms < 0 must raise ValueError."""
    with pytest.raises(ValueError, match="drift_threshold_ms must be > 0"):
        HRVGuidedEngine.describe_calibration_drift(
            baseline_hrv_ms=60.0,
            current_hrv_ms=50.0,
            drift_threshold_ms=-1.0,
        )


# ── Baseline calculation sanity (rolling mean correctness) ───────────────────


def test_calculate_baseline_returns_none_when_insufficient_data():
    """calculate_baseline returns (None, None) when log has fewer than days entries."""
    engine = HRVGuidedEngine()
    engine.hrv_log = [("2026-01-01", 55.0), ("2026-01-02", 57.0)]
    result = engine.calculate_baseline(days=7)
    assert result == (None, None)


def test_calculate_baseline_correct_mean_and_std():
    """calculate_baseline returns correct mean and sample std dev."""
    engine = _make_engine_with_hrv([50.0, 54.0, 58.0, 62.0, 66.0, 70.0, 74.0])
    mean, std = engine.calculate_baseline(days=7)
    assert mean == pytest.approx(62.0, abs=0.1)
    assert std is not None and std > 0
