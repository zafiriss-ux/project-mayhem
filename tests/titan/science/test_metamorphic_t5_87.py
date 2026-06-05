"""T5-87 — Metamorphic testing for ACWR, TSB, HRV, and TRIMP engines.

Metamorphic testing verifies relational properties (metamorphic relations, MRs)
that must hold between multiple executions with structurally related inputs.
It catches bugs that pass unit tests when the exact expected output is unknown
but the relationship between outputs *is* known.

13 MRs across 4 science engines:
  ACWR  → MR-01 to MR-04
  TSB   → MR-05 to MR-07
  HRV   → MR-08 to MR-10
  TRIMP → MR-11 to MR-13
"""

from __future__ import annotations

import pytest

from titan.science.acwr_engine import ACWREngine
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.trimp_engine import TRIMPEngine
from titan.science.tsb_engine import TSBEngine

# ─── helpers ─────────────────────────────────────────────────────────────────


def _tsb_engine(loads: list[float]) -> TSBEngine:
    engine = TSBEngine()
    for idx, load in enumerate(loads):
        engine.add_daily_load(f"2026-01-{idx + 1:02d}", load)
    return engine


def _hrv_engine(readings: list[float], baseline_days: int = 7) -> HRVGuidedEngine:
    engine = HRVGuidedEngine(baseline_days=baseline_days)
    for idx, hrv in enumerate(readings):
        engine.add_hrv_measurement(f"2026-01-{idx + 1:02d}", hrv)
    return engine


# ─── ACWR MRs ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_mr01_acwr_monotone_in_acute_load() -> None:
    """MR-01: Increasing acute load with fixed chronic raises ACWR."""
    chronic = 10.0
    acwr_low, _, _ = ACWREngine.calculate_acwr(acute_7d=42.0, chronic_28d_avg=chronic)
    acwr_mid, _, _ = ACWREngine.calculate_acwr(acute_7d=70.0, chronic_28d_avg=chronic)
    acwr_high, _, _ = ACWREngine.calculate_acwr(acute_7d=112.0, chronic_28d_avg=chronic)

    assert acwr_low is not None and acwr_mid is not None and acwr_high is not None
    assert acwr_low < acwr_mid < acwr_high


@pytest.mark.unit
def test_mr02_acwr_monotone_decreasing_in_chronic_load() -> None:
    """MR-02: Increasing chronic load with fixed acute lowers ACWR."""
    acute = 70.0
    acwr_hi_chronic, _, _ = ACWREngine.calculate_acwr(acute_7d=acute, chronic_28d_avg=20.0)
    acwr_mid_chronic, _, _ = ACWREngine.calculate_acwr(acute_7d=acute, chronic_28d_avg=10.0)
    acwr_lo_chronic, _, _ = ACWREngine.calculate_acwr(acute_7d=acute, chronic_28d_avg=5.0)

    assert acwr_hi_chronic is not None
    assert acwr_mid_chronic is not None
    assert acwr_lo_chronic is not None
    assert acwr_hi_chronic < acwr_mid_chronic < acwr_lo_chronic


@pytest.mark.unit
def test_mr03_acwr_scale_invariance() -> None:
    """MR-03: Scaling both acute and chronic by the same positive factor leaves ACWR unchanged.

    ACWR = acute / (chronic * 7).  Multiplying both by k cancels: k*a / (k*c*7) = a/(c*7).
    """
    base_acwr, _, _ = ACWREngine.calculate_acwr(acute_7d=70.0, chronic_28d_avg=10.0)

    for k in (0.5, 2.0, 5.0, 100.0):
        scaled_acwr, _, _ = ACWREngine.calculate_acwr(
            acute_7d=70.0 * k, chronic_28d_avg=10.0 * k
        )
        assert scaled_acwr == base_acwr, f"Scale factor {k}: expected {base_acwr}, got {scaled_acwr}"


@pytest.mark.unit
def test_mr04_acwr_injury_risk_score_non_decreasing() -> None:
    """MR-04: Higher ACWR must yield an equal or higher injury risk score.

    The ordinal risk score (1–10) must be non-decreasing across the ACWR domain.
    """
    test_points = [0.3, 0.6, 0.85, 1.1, 1.25, 1.4, 1.6, 1.9, 2.5]
    scores = [ACWREngine.injury_risk_score(acwr)[0] for acwr in test_points]

    for i in range(len(scores) - 1):
        assert scores[i] <= scores[i + 1], (
            f"Risk score not non-decreasing: ACWR {test_points[i]} → score {scores[i]}, "
            f"ACWR {test_points[i + 1]} → score {scores[i + 1]}"
        )


# ─── TSB MRs ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_mr05_rest_day_increases_tsb() -> None:
    """MR-05: Appending a zero-load rest day after a training block increases TSB.

    ATL (7-day EMA, α≈0.25) decays faster than CTL (42-day EMA, α≈0.046) on a
    zero-load day, so TSB = CTL − ATL rises.
    """
    base_loads = [100.0] * 14
    e_training = _tsb_engine(base_loads)
    e_rest = _tsb_engine(base_loads + [0.0])

    tsb_training, _ = e_training.calculate_tsb()
    tsb_rest, _ = e_rest.calculate_tsb()

    assert tsb_training is not None and tsb_rest is not None
    assert tsb_rest > tsb_training, (
        f"Rest day should raise TSB: training={tsb_training}, after_rest={tsb_rest}"
    )


@pytest.mark.unit
def test_mr06_non_negative_loads_produce_non_negative_ctl() -> None:
    """MR-06: All loads ≥ 0 → CTL ≥ 0 (EMA of non-negative values stays non-negative)."""
    for load_set in (
        [0.0, 50.0, 100.0, 75.0, 30.0],
        [0.0] * 10,
        [200.0, 0.0, 150.0, 0.0, 100.0],
    ):
        engine = _tsb_engine(load_set)
        ctl = engine.calculate_ctl()
        assert ctl is not None and ctl >= 0.0, f"CTL={ctl} for loads {load_set}"


@pytest.mark.unit
def test_mr07_constant_load_converges_to_steady_state() -> None:
    """MR-07: After many days of constant load L, CTL ≈ ATL ≈ L and TSB ≈ 0.

    This follows from the EMA fixed-point property: with constant input x,
    EMA → x regardless of decay window.
    """
    constant_load = 80.0
    engine = _tsb_engine([constant_load] * 200)

    ctl = engine.calculate_ctl()
    atl = engine.calculate_atl()
    tsb, _ = engine.calculate_tsb()

    assert ctl is not None and atl is not None and tsb is not None
    assert abs(ctl - constant_load) < 0.5, f"CTL should converge to {constant_load}, got {ctl}"
    assert abs(atl - constant_load) < 0.5, f"ATL should converge to {constant_load}, got {atl}"
    assert abs(tsb) < 1.0, f"TSB should converge to ~0, got {tsb}"


# ─── HRV MRs ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_mr08_identical_rr_intervals_yield_zero_rmssd() -> None:
    """MR-08: All successive differences are zero → rMSSD = 0.

    rMSSD = sqrt(mean(diff²)).  Identical intervals → all diffs = 0 → rMSSD = 0.
    """
    for interval in (700.0, 850.0, 1000.0):
        rr = [interval] * 10
        result = HRVGuidedEngine.calculate_rmssd_from_rr_intervals(rr)
        assert result == 0.0, f"Expected 0 rMSSD for constant interval {interval}, got {result}"


@pytest.mark.unit
def test_mr09_date_deduplication_keeps_latest_value() -> None:
    """MR-09: Adding a second measurement for the same date must overwrite the first.

    Garmin syncs may push the same date twice; the engine must deduplicate so that
    the baseline uses only one reading per day.
    """
    engine = HRVGuidedEngine()
    engine.add_hrv_measurement("2026-01-15", 45.0)
    engine.add_hrv_measurement("2026-01-15", 65.0)  # later / more recent

    dates = [d for d, _ in engine.hrv_log]
    values = dict(engine.hrv_log)

    assert dates.count("2026-01-15") == 1, "Duplicate date not deduplicated"
    assert values["2026-01-15"] == 65.0, "Latest value not kept after dedup"


@pytest.mark.unit
def test_mr10_above_baseline_hrv_preserves_planned_session() -> None:
    """MR-10: today_hrv ≥ baseline → the planned session is recommended unchanged.

    If today's HRV is at or above the rolling mean there is no physiological
    reason to downgrade intensity; the engine must return the original session.
    """
    baseline_hrv = 60.0
    engine = _hrv_engine([baseline_hrv] * 7)

    for planned in ("EASY", "TEMPO", "INTERVALS", "PROGRESSIVE"):
        rec, _, _ = engine.get_training_recommendation(
            today_hrv=baseline_hrv + 10.0, planned_session=planned
        )
        assert rec == planned, (
            f"With HRV above baseline, session '{planned}' should not be downgraded "
            f"but got '{rec}'"
        )


# ─── TRIMP MRs ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_mr11_edwards_trimp_linear_in_duration() -> None:
    """MR-11: Edwards TRIMP is linear in duration for the same HR zone.

    TRIMP = duration × zone_multiplier.  Doubling duration must double TRIMP.
    """
    max_hr = 190
    for avg_hr in (114, 140, 162, 181):  # one HR per zone 2-5
        t1, _ = TRIMPEngine.calculate_edwards_trimp(30, avg_hr, max_hr)
        t2, _ = TRIMPEngine.calculate_edwards_trimp(60, avg_hr, max_hr)
        assert t1 is not None and t2 is not None
        assert t2 == 2 * t1, (
            f"avg_hr={avg_hr}: TRIMP(60min)={t2} should be 2×TRIMP(30min)={t1}"
        )


@pytest.mark.unit
def test_mr12_higher_hr_zone_yields_higher_edwards_trimp() -> None:
    """MR-12: A higher HR zone multiplier produces strictly greater TRIMP per unit time.

    Zones are 1–5 (multipliers 1–5).  For the same duration, zone 5 must
    produce more TRIMP than zone 4, which must produce more than zone 3, etc.
    """
    max_hr = 200
    duration = 45
    zone_hrs = [
        105,  # 52.5 % → zone 1 (< 60 %)
        125,  # 62.5 % → zone 2
        145,  # 72.5 % → zone 3
        165,  # 82.5 % → zone 4
        185,  # 92.5 % → zone 5
    ]
    trimps = [TRIMPEngine.calculate_edwards_trimp(duration, hr, max_hr)[0] for hr in zone_hrs]

    for i in range(len(trimps) - 1):
        assert trimps[i] < trimps[i + 1], (
            f"Zone {i + 1} TRIMP={trimps[i]} should be < zone {i + 2} TRIMP={trimps[i + 1]}"
        )


@pytest.mark.unit
def test_mr13_banister_trimp_monotone_in_average_hr() -> None:
    """MR-13: Banister TRIMP is strictly increasing in avg_hr (same duration, resting, max).

    hr_reserve = (avg - rest) / (max - rest).  As avg_hr rises, hr_reserve rises,
    and the exponential weighting amplifies the increase → TRIMP must increase.
    """
    duration = 60
    resting_hr = 50
    max_hr = 190

    avg_hrs = [100, 120, 140, 155, 170]
    trimps = [
        TRIMPEngine.calculate_banister_trimp(duration, hr, resting_hr, max_hr)
        for hr in avg_hrs
    ]

    assert all(t is not None for t in trimps), "Banister TRIMP returned None unexpectedly"
    for i in range(len(trimps) - 1):
        assert trimps[i] < trimps[i + 1], (  # type: ignore[operator]
            f"Banister TRIMP not monotone: avg_hr={avg_hrs[i]} → {trimps[i]}, "
            f"avg_hr={avg_hrs[i + 1]} → {trimps[i + 1]}"
        )
