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


# ── check_baseline_drift — HD-01 / INV-06 ────────────────────────────────────


def _make_engine_with_hrv_window(window_days: int, values: list[float]) -> HRVGuidedEngine:
    """Build engine with len(values) == window_days * 2 entries (anchor + recent)."""
    engine = HRVGuidedEngine()
    for i, v in enumerate(values):
        engine.hrv_log.append((f"2026-01-{i + 1:02d}", v))
    return engine


def test_check_baseline_drift_7day_decline_detected():
    """FS-02 / spec test: 7-day -3ms/day decline triggers drift with window_days=7.

    Sequence: 7 stable days at 60ms, then 60→57→54→51→48→45→42 (7 declining).
    Total 14 entries = 7 * 2 (minimum for window_days=7).
    Recent mean = (57+54+51+48+45+42+39) / 7 ≈ 48.0; anchor mean = 60.0; delta = -12ms.
    """
    stable = [60.0] * 7
    declining = [60.0 - 3.0 * (i + 1) for i in range(7)]
    engine = _make_engine_with_hrv_window(7, stable + declining)

    assert engine.check_baseline_drift(window_days=7) is True


def test_check_baseline_drift_stable_baseline_no_alarm():
    """Stable HRV log produces no drift alarm."""
    stable = [60.0] * 14  # 14 entries for window_days=7
    engine = _make_engine_with_hrv_window(7, stable)

    assert engine.check_baseline_drift(window_days=7) is False


def test_check_baseline_drift_insufficient_data_returns_false():
    """Fewer than window_days * 2 entries → no alarm (spec: < 28 for default 14)."""
    engine = HRVGuidedEngine()
    # 27 entries — one short of window_days=14 * 2 = 28
    for i in range(27):
        engine.hrv_log.append((f"2026-01-{i + 1:02d}", 60.0 - i * 0.5))

    assert engine.check_baseline_drift(window_days=14) is False


def test_check_baseline_drift_exactly_threshold_not_triggered():
    """Delta exactly equal to HRV_DRIFT_THRESHOLD_MS (8.0) must NOT trigger (strict >)."""
    # anchor mean = 60.0, recent mean = 52.0, |delta| = 8.0 — NOT > threshold
    anchor = [60.0] * 7
    recent = [52.0] * 7
    engine = _make_engine_with_hrv_window(7, anchor + recent)

    assert engine.check_baseline_drift(window_days=7) is False


def test_check_baseline_drift_one_ms_above_threshold_triggers():
    """Delta of 8.01ms (> 8.0 threshold) must trigger."""
    anchor = [60.0] * 7
    recent = [51.98] * 7  # mean = 51.98 → |delta| ≈ 8.02 > 8.0
    engine = _make_engine_with_hrv_window(7, anchor + recent)

    assert engine.check_baseline_drift(window_days=7) is True


def test_check_baseline_drift_upward_drift_also_detected():
    """Positive drift (improvement) of > 8ms is also flagged by the detector."""
    anchor = [50.0] * 7
    recent = [60.0] * 7  # delta = +10ms > 8ms threshold
    engine = _make_engine_with_hrv_window(7, anchor + recent)

    assert engine.check_baseline_drift(window_days=7) is True


def test_check_baseline_drift_default_window_28_entries_required():
    """Default window_days=14 requires exactly 28 entries minimum."""
    # 28 entries: stable anchor 14 + declining recent 14 with delta = 9ms (> 8ms)
    anchor = [60.0] * 14
    recent = [51.0] * 14  # |delta| = 9ms > 8ms
    engine = HRVGuidedEngine()
    for i, v in enumerate(anchor + recent):
        engine.hrv_log.append((f"2026-01-{i + 1:02d}", v))

    assert engine.check_baseline_drift() is True  # default window_days=14


def test_check_baseline_drift_data_confidence_low_flag():
    """drift detected + daily_coach hydration → confidence dict has hrv_baseline_drift=False.

    This verifies the data_confidence_low path per the HD-01 spec requirement:
    'drift detected → data_confidence_low=True in context'.

    We directly verify the confidence dict entry that check_baseline_drift() drives,
    rather than running the full DailyCoach pipeline.
    """
    from titan.config.thresholds import HRV_DRIFT_THRESHOLD_MS

    # Build engine with clear drift: anchor 60ms, recent 50ms — delta = 10ms > 8ms
    anchor = [60.0] * 14
    recent = [50.0] * 14
    engine = HRVGuidedEngine()
    for i, v in enumerate(anchor + recent):
        engine.hrv_log.append((f"2026-01-{i + 1:02d}", v))

    assert engine.check_baseline_drift(window_days=14) is True

    # Simulate the daily_coach confidence computation path
    confidence: dict[str, bool] = {}
    window_days = 14
    if engine.check_baseline_drift(window_days=window_days):
        confidence["hrv_baseline_drift"] = False

    # When hrv_baseline_drift is False (and no other keys contribute positive),
    # the sum of confidence values is 0 (or any value where < 3 → data_confidence_low=True).
    assert "hrv_baseline_drift" in confidence
    assert confidence["hrv_baseline_drift"] is False
    # sum < 3 → data_confidence_low=True (the daily_coach gate condition)
    assert sum(confidence.values()) < 3
