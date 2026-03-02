"""
Science Engine Unit Tests — Coverage for previously-untested modules.

Modules covered (P0 / P1 priority gaps identified in coverage audit):
  - AutonomicFusionEngine  (AFI, 48h buffer, parasympathetic guard, readiness constraints)
  - IntensityGovernor      (signal coloring, aggregate gate, session overrides)
  - CriticalSpeedEngine    (CS/D' regression, TTE prediction, tracker EWMA,
                            archetype inference, thermal degradation, GAP correction)
  - VolumeLoadGauge        (TSB/ACWR/glycogen coloring, aggregate color, score, rationale)
  - OutcomeTracker         (decision recording, outcome round-trip, calibration summary)
  - LactateLogic           (LT1/LT2 boundary conditions, tempo volume decision)
"""

import pytest
from typing import List, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# AutonomicFusionEngine
# ──────────────────────────────────────────────────────────────────────────────

class TestAutonomicFusionEngine:
    """Unit tests for AFI calculation, 48h CNS buffer, and parasympathetic guard."""

    @pytest.fixture
    def afe(self):
        from titan.science.autonomic_engine import AutonomicFusionEngine
        return AutonomicFusionEngine()

    def _add_hrr_history(self, afe, values: List[int]) -> None:
        """Helper: populate HRR log with dated entries."""
        for i, v in enumerate(values):
            afe.add_hrr(f"2026-01-{i+1:02d}", v)

    # ── Weight validation ──────────────────────────────────────────────────

    def test_weights_sum_to_one(self, afe):
        total = sum(afe._WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Weights must sum to 1.0, got {total}"

    def test_weights_all_positive(self, afe):
        for name, w in afe._WEIGHTS.items():
            assert w > 0, f"Weight {name} must be positive"

    # ── AFI basic computation ──────────────────────────────────────────────

    def test_afi_all_positive_signals(self, afe):
        afi = afe.calculate_afi(
            ln_rmssd_deviation=1.0,
            hrr_60_today=None,
            sleep_depth_delta=1.0,
            resp_delta=1.0,
        )
        # With ln_rmssd=1.0 (w=0.40) + sleep=1.0 (w=0.15) + resp=1.0 (w=0.10) = 0.65
        assert afi > 0.0
        assert afi <= 1.0

    def test_afi_all_negative_signals(self, afe):
        afi = afe.calculate_afi(
            ln_rmssd_deviation=-1.0,
            hrr_60_today=None,
            sleep_depth_delta=-1.0,
            resp_delta=-1.0,
        )
        assert afi < 0.0
        assert afi >= -1.0

    def test_afi_neutral_signals_returns_zero(self, afe):
        afi = afe.calculate_afi(0.0, None, 0.0, 0.0)
        assert afi == 0.0

    def test_afi_result_rounded_to_three_places(self, afe):
        afi = afe.calculate_afi(0.333, None, 0.222, 0.111)
        assert afi == round(afi, 3)

    def test_afi_clamping_above_one(self, afe):
        """Inputs > 1.0 are clamped — result must remain ≤ 1.0."""
        afi = afe.calculate_afi(5.0, None, 5.0, 5.0)
        assert afi <= 1.0

    def test_afi_clamping_below_minus_one(self, afe):
        """Inputs < -1.0 are clamped — result must remain ≥ -1.0."""
        afi = afe.calculate_afi(-5.0, None, -5.0, -5.0)
        assert afi >= -1.0

    def test_afi_weights_applied_correctly(self, afe):
        """With no HRR, AFI = 0.40*hrv + 0.15*sleep + 0.10*resp."""
        afi = afe.calculate_afi(
            ln_rmssd_deviation=1.0,
            hrr_60_today=None,
            sleep_depth_delta=0.0,
            resp_delta=0.0,
        )
        assert abs(afi - 0.40) < 0.001

    # ── HRR z-score ────────────────────────────────────────────────────────

    def test_hrr_zscore_insufficient_history_returns_zero(self, afe):
        afe.add_hrr("2026-01-01", 35)
        afe.add_hrr("2026-01-02", 38)
        # Only 2 records — threshold is 3
        z = afe._hrr_zscore(36)
        assert z == 0.0

    def test_hrr_zscore_zero_mad_returns_zero(self, afe):
        """All identical values → MAD = 0 → z-score = 0."""
        for i in range(5):
            afe.add_hrr(f"2026-01-{i+1:02d}", 40)
        z = afe._hrr_zscore(40)
        assert z == 0.0

    def test_hrr_zscore_above_median_is_positive(self, afe):
        """Today's HRR well above median → positive z-score."""
        baseline = [30, 31, 32, 33, 34]
        self._add_hrr_history(afe, baseline)
        z = afe._hrr_zscore(50)  # well above median ~32
        assert z > 0

    def test_hrr_zscore_below_median_is_negative(self, afe):
        """Today's HRR well below median → negative z-score."""
        baseline = [50, 52, 54, 56, 58]
        self._add_hrr_history(afe, baseline)
        z = afe._hrr_zscore(20)
        assert z < 0

    def test_afi_hrr_influences_result_when_enough_history(self, afe):
        """With ≥ 3 HRR records, a high HRR should increase AFI."""
        self._add_hrr_history(afe, [25, 27, 29, 31, 33])
        afi_with_good_hrr = afe.calculate_afi(0.0, hrr_60_today=60, sleep_depth_delta=0.0, resp_delta=0.0)
        afi_with_bad_hrr = afe.calculate_afi(0.0, hrr_60_today=5, sleep_depth_delta=0.0, resp_delta=0.0)
        assert afi_with_good_hrr > afi_with_bad_hrr

    # ── 48h CNS Delay Buffer ───────────────────────────────────────────────

    def test_48h_buffer_single_entry_returns_unchanged(self, afe):
        result = afe.apply_48h_buffer(0.6)
        assert result == 0.6

    def test_48h_buffer_formula_applied_correctly(self, afe):
        """AFI_final = (today + 0.5 * yesterday) / 1.5"""
        afe.apply_48h_buffer(0.4)   # yesterday
        result = afe.apply_48h_buffer(0.8)  # today
        expected = round((0.8 + 0.5 * 0.4) / 1.5, 3)
        assert result == expected

    def test_48h_buffer_negative_does_not_go_below_minus_one(self, afe):
        afe.apply_48h_buffer(-1.0)
        result = afe.apply_48h_buffer(-1.0)
        assert result >= -1.0

    def test_48h_buffer_positive_does_not_exceed_one(self, afe):
        afe.apply_48h_buffer(1.0)
        result = afe.apply_48h_buffer(1.0)
        assert result <= 1.0

    def test_48h_buffer_accumulates_history(self, afe):
        for v in [0.2, 0.4, 0.6]:
            afe.apply_48h_buffer(v)
        assert len(afe._afi_history) == 3

    # ── Parasympathetic Saturation Guard ──────────────────────────────────

    def test_guard_triggered_when_hrv_elevated_and_hrr_impaired(self, afe):
        # Build HRR history: baseline ~40 bpm recovery
        self._add_hrr_history(afe, [40, 41, 42, 43, 44])
        # HRV 15% above baseline, HRR = 20 (well below median of ~42 → z < -1.5)
        result = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=15.0,
            hrr_60_today=10,
        )
        assert result['triggered'] is True
        assert result['readiness_clamp'] == 25
        assert 4 in result['disabled_zones']
        assert 5 in result['disabled_zones']

    def test_guard_not_triggered_when_hrv_normal(self, afe):
        self._add_hrr_history(afe, [40, 41, 42, 43, 44])
        result = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=5.0,   # ≤ 10% — not elevated
            hrr_60_today=10,
        )
        assert result['triggered'] is False
        assert result['readiness_clamp'] == 100

    def test_guard_not_triggered_when_hrr_ok(self, afe):
        self._add_hrr_history(afe, [40, 41, 42, 43, 44])
        result = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=15.0,
            hrr_60_today=42,   # near median → z ≈ 0, not impaired
        )
        assert result['triggered'] is False

    def test_guard_not_triggered_without_hrr_data(self, afe):
        """With < 3 HRR records, HRR impairment cannot be assessed."""
        result = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=20.0,
            hrr_60_today=10,
        )
        assert result['triggered'] is False

    def test_guard_result_has_required_keys_when_not_triggered(self, afe):
        result = afe.check_parasympathetic_guard(5.0)
        for key in ('triggered', 'readiness_clamp', 'disabled_zones'):
            assert key in result

    def test_guard_result_has_required_keys_when_triggered(self, afe):
        self._add_hrr_history(afe, [40, 41, 42, 43, 44])
        result = afe.check_parasympathetic_guard(15.0, hrr_60_today=5)
        for key in ('triggered', 'reason', 'readiness_clamp', 'disabled_zones',
                    'prescribed_type', 'action'):
            assert key in result

    # ── Readiness Constraints ──────────────────────────────────────────────

    def test_get_readiness_constraints_structure(self, afe):
        result = afe.get_readiness_constraints(0.5, 5.0)
        for key in ('afi', 'afi_modifier', 'parasympathetic_guard',
                    'readiness_clamp', 'disabled_zones'):
            assert key in result

    def test_get_readiness_constraints_afi_propagated(self, afe):
        result = afe.get_readiness_constraints(0.5, 5.0)
        assert result['afi'] == 0.5

    def test_get_readiness_constraints_positive_afi_positive_modifier(self, afe):
        result = afe.get_readiness_constraints(1.0, 5.0)
        assert result['afi_modifier'] > 0

    def test_get_readiness_constraints_negative_afi_negative_modifier(self, afe):
        result = afe.get_readiness_constraints(-1.0, 5.0)
        assert result['afi_modifier'] < 0

    def test_get_readiness_constraints_guard_propagates_clamp(self, afe):
        """Guard clamp must flow through to the constraints dict."""
        self._add_hrr_history(afe, [40, 41, 42, 43, 44])
        result = afe.get_readiness_constraints(0.5, 15.0, hrr_60_today=5)
        assert result['readiness_clamp'] == 25
        assert result['disabled_zones'] == [4, 5]


# ──────────────────────────────────────────────────────────────────────────────
# IntensityGovernor
# ──────────────────────────────────────────────────────────────────────────────

class TestIntensityGovernor:
    """Unit tests for graduated GREEN/YELLOW/RED intensity gate enforcement."""

    @pytest.fixture
    def gov(self):
        from titan.science.intensity_governor import IntensityGovernor, GateResult
        return IntensityGovernor()

    # ── Signal color helpers ───────────────────────────────────────────────

    @pytest.mark.parametrize("drift,expected", [
        (2.0, "GREEN"),
        (3.5, "GREEN"),    # exactly 3.5 is not > 3.5
        (3.51, "YELLOW"),  # > 3.5 → YELLOW
        (4.9, "YELLOW"),
        (5.0, "YELLOW"),   # exactly 5.0 is not > 5.0
        (5.1, "RED"),
    ])
    def test_drift_coloring(self, gov, drift, expected):
        assert gov._color_drift(drift) == expected

    @pytest.mark.parametrize("glycogen,expected", [
        (3.9, "GREEN"),
        (4.0, "YELLOW"),   # >= 4 → YELLOW
        (5.9, "YELLOW"),
        (6.0, "YELLOW"),   # exactly 6 is not > 6
        (6.1, "RED"),
    ])
    def test_glycogen_coloring(self, gov, glycogen, expected):
        assert gov._color_glycogen(glycogen) == expected

    @pytest.mark.parametrize("fatigue,expected", [
        ("low", "GREEN"),
        ("MEDIUM", "YELLOW"),
        ("medium", "YELLOW"),
        ("HIGH", "RED"),
        ("high", "RED"),
        ("", "GREEN"),
        (None, "GREEN"),
    ])
    def test_fatigue_coloring(self, gov, fatigue, expected):
        assert gov._color_fatigue(fatigue) == expected

    @pytest.mark.parametrize("acwr,expected", [
        (1.0, "GREEN"),
        (1.3, "GREEN"),    # exactly 1.3 is not > 1.3
        (1.31, "YELLOW"),
        (1.5, "YELLOW"),   # exactly 1.5 is not > 1.5
        (1.51, "RED"),
    ])
    def test_acwr_coloring(self, gov, acwr, expected):
        assert gov._color_acwr(acwr) == expected

    @pytest.mark.parametrize("readiness,expected", [
        (70, "GREEN"),
        (55, "GREEN"),     # exactly 55 is not < 55
        (54, "YELLOW"),
        (40, "YELLOW"),    # exactly 40 is not < 40
        (39, "RED"),
    ])
    def test_readiness_coloring(self, gov, readiness, expected):
        assert gov._color_readiness(readiness) == expected

    # ── Aggregate evaluation ───────────────────────────────────────────────

    def test_all_green_signals(self, gov):
        result = gov.evaluate({
            "drift_pct": 2.0,
            "glycogen_debt": 2.0,
            "acwr": 1.1,
            "readiness_score": 80.0,
            "fatigue_level": "low",
        })
        assert result.color == "GREEN"
        assert result.max_zone == 5
        assert result.volume_modifier == 1.0
        assert result.session_override is None

    def test_single_yellow_signal_yields_yellow(self, gov):
        result = gov.evaluate({"drift_pct": 4.0})  # YELLOW
        assert result.color == "YELLOW"
        assert result.max_zone == 3
        assert result.volume_modifier == 0.8

    def test_single_red_signal_yields_red(self, gov):
        result = gov.evaluate({"drift_pct": 6.0})  # RED
        assert result.color == "RED"
        assert result.max_zone == 2
        assert result.volume_modifier == 0.0
        assert result.session_override == "EASY"

    def test_red_overrides_yellow(self, gov):
        """One RED anywhere → aggregate is RED regardless of other colors."""
        result = gov.evaluate({
            "drift_pct": 2.0,          # GREEN
            "glycogen_debt": 7.0,       # RED
            "readiness_score": 52.0,    # YELLOW
        })
        assert result.color == "RED"

    def test_empty_signals_is_green(self, gov):
        result = gov.evaluate({})
        assert result.color == "GREEN"
        assert result.max_zone == 5

    def test_none_signals_is_green(self, gov):
        result = gov.evaluate(None)
        assert result.color == "GREEN"

    # ── Session override logic ─────────────────────────────────────────────

    def test_yellow_overrides_hammer_to_tempo(self, gov):
        result = gov.evaluate({
            "drift_pct": 4.0,           # YELLOW
            "planned_session": "HAMMER",
        })
        assert result.session_override == "TEMPO"

    def test_yellow_overrides_race_to_tempo(self, gov):
        result = gov.evaluate({
            "drift_pct": 4.0,
            "planned_session": "RACE",
        })
        assert result.session_override == "TEMPO"

    def test_yellow_no_override_for_easy(self, gov):
        result = gov.evaluate({
            "drift_pct": 4.0,
            "planned_session": "EASY",
        })
        assert result.session_override is None

    def test_yellow_no_override_for_long(self, gov):
        result = gov.evaluate({
            "drift_pct": 4.0,
            "planned_session": "LONG",
        })
        assert result.session_override is None

    def test_red_always_overrides_to_easy(self, gov):
        result = gov.evaluate({
            "drift_pct": 6.0,           # RED
            "planned_session": "EASY",
        })
        assert result.session_override == "EASY"

    # ── Triggered signals list ─────────────────────────────────────────────

    def test_triggered_signals_populated_correctly(self, gov):
        result = gov.evaluate({
            "drift_pct": 4.0,           # YELLOW → triggered
            "glycogen_debt": 2.0,       # GREEN → not triggered
            "fatigue_level": "HIGH",    # RED → triggered
        })
        assert "drift" in result.triggered_signals
        assert "fatigue" in result.triggered_signals
        assert "glycogen_debt" not in result.triggered_signals

    def test_triggered_signals_empty_when_all_green(self, gov):
        result = gov.evaluate({
            "drift_pct": 2.0,
            "glycogen_debt": 1.0,
            "readiness_score": 80.0,
        })
        assert result.triggered_signals == []

    # ── Audit dict structure ───────────────────────────────────────────────

    def test_audit_contains_aggregate_key(self, gov):
        result = gov.evaluate({"drift_pct": 2.0})
        assert "aggregate" in result.audit

    def test_audit_contains_applied_constraints(self, gov):
        result = gov.evaluate({"drift_pct": 2.0})
        assert "applied_constraints" in result.audit
        c = result.audit["applied_constraints"]
        assert "max_zone" in c and "volume_modifier" in c and "session_override" in c

    def test_audit_signal_entry_has_required_keys(self, gov):
        result = gov.evaluate({"drift_pct": 4.0})
        entry = result.audit["drift"]
        for key in ("value", "signal_color", "threshold_yellow", "threshold_red"):
            assert key in entry

    # ── Return type ────────────────────────────────────────────────────────

    def test_evaluate_returns_gate_result(self, gov):
        from titan.science.intensity_governor import GateResult
        result = gov.evaluate({})
        assert isinstance(result, GateResult)

    def test_gate_result_has_all_fields(self, gov):
        result = gov.evaluate({"drift_pct": 2.0})
        assert hasattr(result, 'color')
        assert hasattr(result, 'max_zone')
        assert hasattr(result, 'volume_modifier')
        assert hasattr(result, 'session_override')
        assert hasattr(result, 'triggered_signals')
        assert hasattr(result, 'audit')


# ──────────────────────────────────────────────────────────────────────────────
# CriticalSpeedEngine
# ──────────────────────────────────────────────────────────────────────────────

class TestCriticalSpeedEngine:
    """Tests for CS/D' regression and time-to-exhaustion prediction."""

    @pytest.fixture
    def cse(self):
        from titan.science.critical_speed import CriticalSpeedEngine
        return CriticalSpeedEngine()

    # ── estimate_cs_and_dprime ─────────────────────────────────────────────

    def test_returns_none_none_for_single_performance(self, cse):
        cs, dp = cse.estimate_cs_and_dprime([(3000, 720)])
        assert cs is None and dp is None

    def test_returns_none_none_for_empty_list(self, cse):
        cs, dp = cse.estimate_cs_and_dprime([])
        assert cs is None and dp is None

    def test_valid_cs_from_two_performances(self, cse):
        perfs = [(3000, 720), (10000, 2700)]
        cs, dp = cse.estimate_cs_and_dprime(perfs)
        assert cs is not None and dp is not None
        assert cs > 0  # speed must be positive

    def test_valid_cs_from_three_performances(self, cse):
        perfs = [(3000, 720), (5000, 1260), (10000, 2700)]
        cs, dp = cse.estimate_cs_and_dprime(perfs)
        assert cs is not None and dp is not None

    def test_zero_time_entries_filtered(self, cse):
        perfs = [(3000, 0), (5000, 1260), (10000, 2700)]  # first has zero time
        cs, dp = cse.estimate_cs_and_dprime(perfs)
        assert cs is not None

    def test_all_zero_time_returns_none(self, cse):
        perfs = [(3000, 0), (5000, 0)]
        cs, dp = cse.estimate_cs_and_dprime(perfs)
        assert cs is None and dp is None

    def test_cs_is_slope_of_distance_time_regression(self, cse):
        """Perfect linear relationship: d=CS*t+D'. Verify regression recovers CS."""
        CS_TRUE = 3.5  # m/s
        D_TRUE = 200.0
        perfs = [(CS_TRUE * t + D_TRUE, t) for t in [600, 900, 1200, 1500]]
        cs, dp = cse.estimate_cs_and_dprime(perfs)
        assert abs(cs - CS_TRUE) < 0.01
        assert abs(dp - D_TRUE) < 5.0

    # ── time_to_exhaustion_at_pace ─────────────────────────────────────────

    def test_tte_pace_at_or_below_cs_is_none(self, cse):
        """Sustainable pace → no exhaustion predicted."""
        cs = 3.5  # m/s → 285.7 s/km
        d_prime = 200.0
        sustainable_pace = 1000.0 / cs  # = 285.7 s/km
        tte = cse.time_to_exhaustion_at_pace(cs, d_prime, sustainable_pace)
        assert tte is None

    def test_tte_pace_above_cs_returns_positive(self, cse):
        cs = 3.5
        d_prime = 200.0
        hard_pace = 250.0  # s/km → 4.0 m/s > 3.5 CS
        tte = cse.time_to_exhaustion_at_pace(cs, d_prime, hard_pace)
        assert tte is not None and tte > 0

    def test_tte_formula_is_correct(self, cse):
        """t = D' / (v - CS)"""
        cs = 3.0
        d_prime = 300.0
        pace_sec_per_km = 250.0  # v = 1000/250 = 4.0 m/s
        v = 1000.0 / 250.0
        expected = d_prime / (v - cs)
        tte = cse.time_to_exhaustion_at_pace(cs, d_prime, pace_sec_per_km)
        assert abs(tte - expected) < 0.01

    def test_tte_returns_none_if_cs_is_none(self, cse):
        tte = cse.time_to_exhaustion_at_pace(None, 200.0, 250.0)
        assert tte is None

    def test_tte_returns_none_if_dprime_is_none(self, cse):
        tte = cse.time_to_exhaustion_at_pace(3.5, None, 250.0)
        assert tte is None

    def test_tte_returns_none_for_zero_pace(self, cse):
        tte = cse.time_to_exhaustion_at_pace(3.5, 200.0, 0.0)
        assert tte is None

    def test_tte_faster_pace_gives_shorter_tte(self, cse):
        cs, d_prime = 3.0, 300.0
        tte_moderate = cse.time_to_exhaustion_at_pace(cs, d_prime, 280.0)
        tte_fast = cse.time_to_exhaustion_at_pace(cs, d_prime, 240.0)
        assert tte_fast < tte_moderate


class TestCriticalSpeedTracker:
    """Tests for stateful EWMA tracker, archetype inference, thermal model, GAP."""

    @pytest.fixture
    def tracker(self):
        from titan.science.critical_speed import CriticalSpeedTracker
        return CriticalSpeedTracker()

    # ── EWMA smoothing ─────────────────────────────────────────────────────

    def test_first_update_sets_smoothed_to_raw(self, tracker):
        tracker.update("2026-01-01", 3.5, 200.0)
        assert tracker.cs_smoothed == 3.5

    def test_ewma_smoothing_applied_on_second_update(self, tracker):
        tracker.update("2026-01-01", 3.5, 200.0)
        tracker.update("2026-01-15", 4.0, 220.0)
        alpha = 0.3
        expected = alpha * 4.0 + (1 - alpha) * 3.5
        assert abs(tracker.cs_smoothed - expected) < 0.001

    def test_ewma_converges_toward_new_value(self, tracker):
        tracker.update("2026-01-01", 3.0, 200.0)
        for i in range(20):
            tracker.update(f"2026-02-{i+1:02d}", 4.0, 200.0)
        assert tracker.cs_smoothed > 3.8  # should have converged substantially

    def test_history_accumulates(self, tracker):
        tracker.update("2026-01-01", 3.5, 200.0)
        tracker.update("2026-01-15", 3.6, 205.0)
        assert len(tracker.cs_raw_history) == 2

    # ── Archetype inference ────────────────────────────────────────────────

    def test_archetype_speed_when_high_dprime_cs_ratio(self, tracker):
        """D'/CS > 300 → SPEED archetype."""
        tracker.update("2026-01-01", 3.0, 1000.0)  # ratio = 333
        assert tracker.archetype == "SPEED"

    def test_archetype_endurance_when_low_dprime_cs_ratio(self, tracker):
        """D'/CS < 150 → ENDURANCE archetype."""
        tracker.update("2026-01-01", 4.0, 400.0)  # ratio = 100
        assert tracker.archetype == "ENDURANCE"

    def test_archetype_hybrid_when_middle_ratio(self, tracker):
        """150 ≤ D'/CS ≤ 300 → HYBRID archetype."""
        tracker.update("2026-01-01", 4.0, 800.0)  # ratio = 200
        assert tracker.archetype == "HYBRID"

    def test_archetype_default_is_hybrid_before_update(self, tracker):
        assert tracker.archetype == "HYBRID"

    def test_tau_multiplier_speed(self, tracker):
        tracker.update("2026-01-01", 3.0, 1000.0)  # SPEED
        assert tracker.tau_w_prime_multiplier == 1.175

    def test_tau_multiplier_endurance(self, tracker):
        tracker.update("2026-01-01", 4.0, 400.0)  # ENDURANCE
        assert tracker.tau_w_prime_multiplier == 0.925

    def test_tau_multiplier_hybrid(self, tracker):
        tracker.update("2026-01-01", 4.0, 800.0)  # HYBRID
        assert tracker.tau_w_prime_multiplier == 1.0

    # ── Thermal degradation ────────────────────────────────────────────────

    def test_thermal_below_20c_no_degradation(self, tracker):
        tracker.update("2026-01-01", 4.0, 200.0)
        cs_20 = tracker.apply_thermal(20.0)
        assert cs_20 == round(tracker.cs_smoothed, 3)

    def test_thermal_at_0c_no_degradation(self, tracker):
        tracker.update("2026-01-01", 4.0, 200.0)
        cs_cold = tracker.apply_thermal(0.0)
        assert cs_cold == round(tracker.cs_smoothed, 3)

    def test_thermal_at_25c_applies_degradation(self, tracker):
        tracker.update("2026-01-01", 4.0, 200.0)
        cs_hot = tracker.apply_thermal(25.0)
        # 5°C above threshold → 1 band → factor = 1 - 0.025*1 = 0.975
        expected = round(4.0 * 0.975, 3)
        assert cs_hot == expected

    def test_thermal_at_30c_more_degradation(self, tracker):
        tracker.update("2026-01-01", 4.0, 200.0)
        cs_25 = tracker.apply_thermal(25.0)
        cs_30 = tracker.apply_thermal(30.0)
        assert cs_30 < cs_25

    def test_thermal_floor_at_85_percent(self, tracker):
        """Extreme heat should not degrade CS below 85% of smoothed."""
        tracker.update("2026-01-01", 4.0, 200.0)
        cs_extreme = tracker.apply_thermal(100.0)  # very hot
        assert cs_extreme >= round(4.0 * 0.85, 3)

    def test_thermal_returns_none_before_update(self, tracker):
        result = tracker.apply_thermal(30.0)
        assert result is None

    # ── GAP correction (static) ────────────────────────────────────────────

    @pytest.mark.parametrize("gradient,base_pace,expected_gap", [
        (0.0, 300.0, 300.0),   # flat: no change
        (5.0, 300.0, 250.0),   # 5% uphill: adjustment=50 → 300-50=250
        (-5.0, 300.0, 325.0),  # 5% downhill: adjustment=-25 → 300-(-25)=325
    ])
    def test_gap_adjustment_direction(self, gradient, base_pace, expected_gap):
        from titan.science.critical_speed import CriticalSpeedTracker
        gap = CriticalSpeedTracker.gap_correct_pace(base_pace, gradient)
        assert abs(gap - expected_gap) < 0.01

    def test_gap_uphill_gives_lower_gap_than_flat(self):
        from titan.science.critical_speed import CriticalSpeedTracker
        gap_flat = CriticalSpeedTracker.gap_correct_pace(300.0, 0.0)
        gap_uphill = CriticalSpeedTracker.gap_correct_pace(300.0, 10.0)
        # Uphill running is harder → flatter-equivalent is faster (lower s/km)
        assert gap_uphill < gap_flat

    def test_gap_floored_at_60(self):
        """Very steep downhill cannot produce GAP pace below 60 s/km."""
        from titan.science.critical_speed import CriticalSpeedTracker
        gap = CriticalSpeedTracker.gap_correct_pace(100.0, -50.0)  # steep downhill
        assert gap >= 60.0

    # ── Confidence ─────────────────────────────────────────────────────────

    def test_confidence_zero_before_any_update(self, tracker):
        assert tracker.confidence == 0.0

    def test_confidence_increases_with_more_updates(self, tracker):
        tracker.update("2026-01-01", 3.5, 200.0)
        c1 = tracker.confidence
        tracker.update("2026-01-15", 3.6, 205.0)
        c2 = tracker.confidence
        tracker.update("2026-02-01", 3.7, 210.0)
        c3 = tracker.confidence
        assert c1 < c2 < c3

    def test_confidence_bounded_zero_to_one(self, tracker):
        for i in range(10):
            tracker.update(f"2026-01-{i+1:02d}", 3.5 + i * 0.01, 200.0)
        assert 0.0 <= tracker.confidence <= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# VolumeLoadGauge
# ──────────────────────────────────────────────────────────────────────────────

class TestVolumeLoadGauge:
    """Tests for TSB/ACWR/glycogen signal aggregation and VLGState output."""

    @pytest.fixture
    def vlg(self):
        from titan.science.volume_load_gauge import VolumeLoadGauge
        return VolumeLoadGauge()

    # ── Individual signal colors ────────────────────────────────────────────

    @pytest.mark.parametrize("tsb,expected", [
        (0.0, "GREEN"),
        (-29.0, "GREEN"),
        (-30.0, "YELLOW"),  # ≤ -30
        (-49.0, "YELLOW"),
        (-50.0, "RED"),     # ≤ -50
        (-100.0, "RED"),
    ])
    def test_tsb_color(self, vlg, tsb, expected):
        assert vlg._tsb_color(tsb) == expected

    @pytest.mark.parametrize("acwr,expected", [
        (1.0, "GREEN"),
        (0.8, "GREEN"),    # exactly 0.8 is not < 0.8
        (0.79, "YELLOW"),
        (1.3, "GREEN"),    # exactly 1.3 is not > 1.3
        (1.31, "YELLOW"),
        (0.7, "YELLOW"),   # exactly 0.7 is not < 0.7
        (1.5, "YELLOW"),   # > 1.5 → RED, but 1.5 is not > 1.5
        (1.51, "RED"),
        (0.69, "RED"),     # < 0.7 → RED
    ])
    def test_acwr_color(self, vlg, acwr, expected):
        assert vlg._acwr_color(acwr) == expected

    @pytest.mark.parametrize("glycogen,expected", [
        (3.9, "GREEN"),
        (4.0, "YELLOW"),   # >= 4 → YELLOW
        (6.9, "YELLOW"),
        (7.0, "RED"),      # >= 7 → RED
        (10.0, "RED"),
    ])
    def test_glycogen_color(self, vlg, glycogen, expected):
        assert vlg._glycogen_color(glycogen) == expected

    # ── resolve() aggregate color ──────────────────────────────────────────

    def test_all_green_returns_green(self, vlg):
        state = vlg.resolve(tsb_value=0.0, acwr=1.0, glycogen_debt=2.0)
        assert state.color == "GREEN"

    def test_single_yellow_returns_yellow(self, vlg):
        state = vlg.resolve(tsb_value=-35.0, acwr=1.0, glycogen_debt=2.0)
        assert state.color == "YELLOW"

    def test_single_red_returns_red(self, vlg):
        state = vlg.resolve(tsb_value=-55.0, acwr=1.0, glycogen_debt=2.0)
        assert state.color == "RED"

    def test_red_overrides_yellow(self, vlg):
        state = vlg.resolve(tsb_value=-55.0, acwr=1.35, glycogen_debt=5.0)
        assert state.color == "RED"

    def test_multiple_yellows_stay_yellow(self, vlg):
        state = vlg.resolve(tsb_value=-35.0, acwr=1.35, glycogen_debt=5.0)
        assert state.color == "YELLOW"

    # ── Score calculation ──────────────────────────────────────────────────

    def test_all_green_score_is_zero(self, vlg):
        state = vlg.resolve(0.0, 1.0, 2.0)
        assert state.score == 0

    def test_one_yellow_score_is_one(self, vlg):
        state = vlg.resolve(-35.0, 1.0, 2.0)
        assert state.score == 1

    def test_two_yellows_score_is_two(self, vlg):
        state = vlg.resolve(-35.0, 1.35, 2.0)
        assert state.score == 2

    def test_one_red_score_is_two(self, vlg):
        state = vlg.resolve(-55.0, 1.0, 2.0)
        assert state.score == 2

    def test_one_red_one_yellow_score_is_three(self, vlg):
        state = vlg.resolve(-55.0, 1.35, 2.0)
        assert state.score == 3

    # ── Components dict ────────────────────────────────────────────────────

    def test_components_always_has_three_keys(self, vlg):
        state = vlg.resolve(0.0, 1.0, 2.0)
        assert set(state.components.keys()) == {"tsb", "acwr", "glycogen"}

    def test_components_reflect_individual_colors(self, vlg):
        state = vlg.resolve(-35.0, 1.0, 7.0)
        assert state.components["tsb"] == "YELLOW"
        assert state.components["acwr"] == "GREEN"
        assert state.components["glycogen"] == "RED"

    # ── Rationale ──────────────────────────────────────────────────────────

    def test_rationale_all_green_is_positive_message(self, vlg):
        state = vlg.resolve(0.0, 1.0, 2.0)
        assert len(state.rationale) == 1
        assert "green" in state.rationale[0].lower()

    def test_rationale_includes_tsb_when_not_green(self, vlg):
        state = vlg.resolve(-35.0, 1.0, 2.0)
        assert any("TSB" in r for r in state.rationale)

    def test_rationale_includes_acwr_when_not_green(self, vlg):
        state = vlg.resolve(0.0, 1.35, 2.0)
        assert any("ACWR" in r for r in state.rationale)

    def test_rationale_includes_glycogen_when_not_green(self, vlg):
        state = vlg.resolve(0.0, 1.0, 5.0)
        assert any("Glycogen" in r for r in state.rationale)

    # ── VLGState immutability ──────────────────────────────────────────────

    def test_vlg_state_is_frozen(self, vlg):
        from titan.science.volume_load_gauge import VLGState
        state = vlg.resolve(0.0, 1.0, 2.0)
        assert isinstance(state, VLGState)
        with pytest.raises((AttributeError, TypeError)):
            state.color = "BLUE"  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────────
# OutcomeTracker
# ──────────────────────────────────────────────────────────────────────────────

class TestOutcomeTracker:
    """Tests for governance decision recording, outcome attachment, and calibration."""

    @pytest.fixture
    def tracker(self):
        from titan.science.outcome_tracker import OutcomeTracker
        return OutcomeTracker()

    _APL_RESULT = {"priority_vector": {"HARD_STOP_SAFETY_GATES": 1}, "lock_thresholds": {}}

    def _make_decision(self, tracker, **kwargs):
        defaults = dict(
            session_planned="VO2MAX",
            session_post_governance="EASY",
            locks_applied=["HARD_STOP_SAFETY_GATES"],
            governance_clean=False,
            phase="BUILD",
            vlg_color="YELLOW",
            apl_result=self._APL_RESULT,
            acwr=1.1,
            tsb_value=-20.0,
            readiness_score=70.0,
            glycogen_debt=3.0,
            date="2026-03-01",
        )
        defaults.update(kwargs)
        return tracker.record_decision(**defaults)

    # ── record_decision ────────────────────────────────────────────────────

    def test_record_decision_returns_governance_decision(self, tracker):
        from titan.science.outcome_tracker import GovernanceDecision
        decision = self._make_decision(tracker)
        assert isinstance(decision, GovernanceDecision)

    def test_record_decision_increments_stored_decisions(self, tracker):
        self._make_decision(tracker, date="2026-03-01")
        self._make_decision(tracker, date="2026-03-02")
        assert len(tracker.get_decisions()) == 2

    def test_record_decision_stores_correct_fields(self, tracker):
        decision = self._make_decision(
            tracker,
            session_planned="VO2MAX",
            session_post_governance="EASY",
            governance_clean=False,
            phase="BUILD",
            vlg_color="YELLOW",
            acwr=1.15,
            tsb_value=-22.0,
            readiness_score=68.0,
            glycogen_debt=4.5,
        )
        assert decision.session_planned == "VO2MAX"
        assert decision.session_post_governance == "EASY"
        assert decision.governance_clean is False
        assert decision.phase == "BUILD"
        assert decision.vlg_color == "YELLOW"
        assert abs(decision.acwr - 1.15) < 0.001

    def test_record_decision_uses_today_when_no_date(self, tracker):
        from datetime import datetime
        decision = tracker.record_decision(
            session_planned="EASY",
            session_post_governance="EASY",
            locks_applied=[],
            governance_clean=True,
            phase="BASE",
            vlg_color="GREEN",
            apl_result=self._APL_RESULT,
            acwr=1.0,
            tsb_value=0.0,
            readiness_score=80.0,
            glycogen_debt=1.0,
        )
        today = datetime.now().strftime('%Y-%m-%d')
        assert decision.date == today

    def test_record_decision_afi_value_stored(self, tracker):
        decision = self._make_decision(tracker, afi_value=0.65)
        assert decision.afi_value == 0.65

    def test_record_decision_afi_none_stored(self, tracker):
        decision = self._make_decision(tracker)
        assert decision.afi_value is None

    # ── record_outcome ─────────────────────────────────────────────────────

    def test_record_outcome_returns_true_when_found(self, tracker):
        self._make_decision(tracker, date="2026-03-01")
        result = tracker.record_outcome("2026-03-01", rpe=6, completed=True)
        assert result is True

    def test_record_outcome_returns_false_when_not_found(self, tracker):
        result = tracker.record_outcome("2026-03-01", rpe=6, completed=True)
        assert result is False

    def test_record_outcome_populates_decision_fields(self, tracker):
        decision = self._make_decision(tracker, date="2026-03-01")
        tracker.record_outcome(
            "2026-03-01",
            rpe=7,
            completed=True,
            actual_session_type="TEMPO",
            notes="felt good",
        )
        assert decision.outcome_rpe == 7
        assert decision.outcome_completed is True
        assert decision.outcome_session_type_actual == "TEMPO"
        assert decision.outcome_notes == "felt good"

    def test_record_outcome_detects_deviation(self, tracker):
        """Athlete did different session than governance prescribed."""
        decision = self._make_decision(
            tracker, date="2026-03-01", session_post_governance="EASY"
        )
        tracker.record_outcome("2026-03-01", actual_session_type="TEMPO")
        # The deviation is logged but not stored on decision as a flag field directly;
        # verify outcome_session_type_actual was recorded
        assert decision.outcome_session_type_actual == "TEMPO"

    def test_record_outcome_finds_most_recent_when_duplicate_dates(self, tracker):
        d1 = self._make_decision(tracker, date="2026-03-01", session_post_governance="EASY")
        d2 = self._make_decision(tracker, date="2026-03-01", session_post_governance="TEMPO")
        tracker.record_outcome("2026-03-01", completed=True)
        # Most recent (reversed search) should be updated
        assert d2.outcome_completed is True
        assert d1.outcome_completed is None

    # ── get_decisions ──────────────────────────────────────────────────────

    def test_get_decisions_returns_all(self, tracker):
        self._make_decision(tracker, date="2026-03-01")
        self._make_decision(tracker, date="2026-03-02")
        assert len(tracker.get_decisions()) == 2

    def test_get_decisions_filter_by_date(self, tracker):
        self._make_decision(tracker, date="2026-03-01")
        self._make_decision(tracker, date="2026-03-02")
        result = tracker.get_decisions(date="2026-03-01")
        assert len(result) == 1
        assert result[0].date == "2026-03-01"

    def test_get_decisions_filter_by_phase(self, tracker):
        self._make_decision(tracker, date="2026-03-01", phase="BUILD")
        self._make_decision(tracker, date="2026-03-02", phase="BASE")
        result = tracker.get_decisions(phase="BUILD")
        assert len(result) == 1

    def test_get_decisions_phase_filter_case_insensitive(self, tracker):
        self._make_decision(tracker, date="2026-03-01", phase="BUILD")
        assert len(tracker.get_decisions(phase="build")) == 1

    def test_get_decisions_with_outcomes_only(self, tracker):
        self._make_decision(tracker, date="2026-03-01")
        self._make_decision(tracker, date="2026-03-02")
        tracker.record_outcome("2026-03-01", completed=True)
        result = tracker.get_decisions(with_outcomes_only=True)
        assert len(result) == 1

    # ── get_lock_rate_by_phase ─────────────────────────────────────────────

    def test_lock_rate_by_phase_all_locked(self, tracker):
        self._make_decision(tracker, phase="BUILD", governance_clean=False)
        self._make_decision(tracker, phase="BUILD", governance_clean=False)
        rates = tracker.get_lock_rate_by_phase()
        assert rates["BUILD"] == 1.0

    def test_lock_rate_by_phase_none_locked(self, tracker):
        self._make_decision(tracker, phase="BASE", governance_clean=True, locks_applied=[])
        rates = tracker.get_lock_rate_by_phase()
        assert rates["BASE"] == 0.0

    def test_lock_rate_by_phase_mixed(self, tracker):
        self._make_decision(tracker, phase="PEAK", governance_clean=False)
        self._make_decision(tracker, phase="PEAK", governance_clean=True, locks_applied=[])
        rates = tracker.get_lock_rate_by_phase()
        assert abs(rates["PEAK"] - 0.5) < 0.001

    # ── get_calibration_summary ────────────────────────────────────────────

    def test_calibration_summary_no_outcomes(self, tracker):
        self._make_decision(tracker)
        summary = tracker.get_calibration_summary()
        assert summary["status"] == "NO_OUTCOMES_YET"
        assert summary["n_decisions"] == 1
        assert summary["n_with_outcome"] == 0

    def test_calibration_summary_accumulating(self, tracker):
        for i in range(5):
            d = self._make_decision(tracker, date=f"2026-01-{i+1:02d}")
            tracker.record_outcome(f"2026-01-{i+1:02d}", completed=True, rpe=6)
        summary = tracker.get_calibration_summary()
        assert summary["status"] == "ACCUMULATING"
        assert summary["n_with_outcome"] == 5

    def test_calibration_summary_ready_at_30(self, tracker):
        for i in range(30):
            day = f"2026-01-{i+1:02d}" if i < 31 else f"2026-02-{i-30:02d}"
            self._make_decision(tracker, date=day)
            tracker.record_outcome(day, completed=True)
        summary = tracker.get_calibration_summary()
        assert summary["status"] == "CALIBRATION_AVAILABLE"

    def test_calibration_summary_rates_computed(self, tracker):
        for i in range(4):
            day = f"2026-01-{i+1:02d}"
            clean = (i % 2 == 0)
            self._make_decision(tracker, date=day, governance_clean=clean,
                                locks_applied=[] if clean else ["HARD_STOP_SAFETY_GATES"])
            tracker.record_outcome(day, completed=True, rpe=7)
        summary = tracker.get_calibration_summary()
        assert "governance_lock_rate" in summary
        assert "completion_rate" in summary
        assert summary["completion_rate"] == 1.0
        assert "lock_outcome_correlation" in summary

    def test_lock_outcome_correlation_returns_empty_without_outcomes(self, tracker):
        self._make_decision(tracker, locks_applied=["LOCK_A"], governance_clean=False)
        assert tracker.get_lock_outcome_correlation() == {}

    def test_lock_outcome_correlation_computes_completion_delta(self, tracker):
        for i in range(4):
            day = f"2026-02-{i+1:02d}"
            self._make_decision(
                tracker,
                date=day,
                governance_clean=False,
                locks_applied=["LOCK_A"],
            )
            tracker.record_outcome(day, completed=(i != 0), rpe=8)

        for i in range(4):
            day = f"2026-03-{i+1:02d}"
            self._make_decision(
                tracker,
                date=day,
                governance_clean=True,
                locks_applied=[],
            )
            tracker.record_outcome(day, completed=True, rpe=5)

        corr = tracker.get_lock_outcome_correlation()
        assert "LOCK_A" in corr
        assert corr["LOCK_A"]["n_with_lock"] == 4
        assert corr["LOCK_A"]["n_without_lock"] == 4
        assert corr["LOCK_A"]["completion_with_lock"] == 0.75
        assert corr["LOCK_A"]["completion_without_lock"] == 1.0
        assert corr["LOCK_A"]["completion_delta_pp"] == -25.0

    def test_calibration_summary_avg_rpe(self, tracker):
        for i, rpe in enumerate([5, 7]):
            day = f"2026-01-{i+1:02d}"
            self._make_decision(tracker, date=day)
            tracker.record_outcome(day, completed=True, rpe=rpe)
        summary = tracker.get_calibration_summary()
        assert abs(summary["avg_rpe_when_completed"] - 6.0) < 0.1


# ──────────────────────────────────────────────────────────────────────────────
# LactateLogic — boundary conditions
# ──────────────────────────────────────────────────────────────────────────────

class TestLactateLogic:
    """Boundary tests for LT1/LT2 detection and tempo volume decision."""

    @pytest.fixture
    def lt(self):
        from titan.science.lactate_logic import LactateLogic
        return LactateLogic()

    # ── estimate_lt1 ───────────────────────────────────────────────────────

    def test_lt1_true_when_low_drift_and_low_hr(self, lt):
        result = lt.estimate_lt1(hr_percent_max=70.0, drift_percent=2.0)
        assert result["is_lt1"] is True

    def test_lt1_false_when_drift_too_high(self, lt):
        result = lt.estimate_lt1(hr_percent_max=70.0, drift_percent=3.5)
        assert result["is_lt1"] is False

    def test_lt1_false_when_hr_too_high(self, lt):
        result = lt.estimate_lt1(hr_percent_max=80.0, drift_percent=1.0)
        assert result["is_lt1"] is False

    def test_lt1_false_when_both_exceed_thresholds(self, lt):
        result = lt.estimate_lt1(hr_percent_max=82.0, drift_percent=4.0)
        assert result["is_lt1"] is False

    def test_lt1_boundary_drift_exactly_3_is_false(self, lt):
        """drift < 3.0 is required — exactly 3.0 fails."""
        result = lt.estimate_lt1(hr_percent_max=70.0, drift_percent=3.0)
        assert result["is_lt1"] is False

    def test_lt1_boundary_drift_just_below_3_is_true(self, lt):
        result = lt.estimate_lt1(hr_percent_max=70.0, drift_percent=2.99)
        assert result["is_lt1"] is True

    def test_lt1_boundary_hr_exactly_78_is_true(self, lt):
        """hr_percent_max ≤ 78.0 — exactly 78.0 passes."""
        result = lt.estimate_lt1(hr_percent_max=78.0, drift_percent=2.0)
        assert result["is_lt1"] is True

    def test_lt1_boundary_hr_above_78_is_false(self, lt):
        result = lt.estimate_lt1(hr_percent_max=78.1, drift_percent=2.0)
        assert result["is_lt1"] is False

    def test_lt1_result_has_required_keys(self, lt):
        result = lt.estimate_lt1(70.0, 2.0)
        for key in ("is_lt1", "status_text", "hr_pct_max", "drift_pct"):
            assert key in result

    def test_lt1_status_text_reflects_result(self, lt):
        true_result = lt.estimate_lt1(70.0, 2.0)
        false_result = lt.estimate_lt1(80.0, 4.0)
        assert "TRUE" in true_result["status_text"]
        assert "FALSE" in false_result["status_text"]

    def test_lt1_values_rounded(self, lt):
        result = lt.estimate_lt1(70.12345, 2.56789)
        assert result["hr_pct_max"] == round(70.12345, 1)
        assert result["drift_pct"] == round(2.56789, 1)

    # ── estimate_lt2 ───────────────────────────────────────────────────────

    def test_lt2_true_when_stable_and_rpe_in_range(self, lt):
        result = lt.estimate_lt2(hr_stable=True, rpe=6.5)
        assert result["is_lt2"] is True

    def test_lt2_false_when_hr_unstable(self, lt):
        result = lt.estimate_lt2(hr_stable=False, rpe=6.5)
        assert result["is_lt2"] is False

    def test_lt2_false_when_rpe_below_range(self, lt):
        result = lt.estimate_lt2(hr_stable=True, rpe=5.9)
        assert result["is_lt2"] is False

    def test_lt2_false_when_rpe_above_range(self, lt):
        result = lt.estimate_lt2(hr_stable=True, rpe=7.1)
        assert result["is_lt2"] is False

    def test_lt2_boundary_rpe_6_is_true(self, lt):
        """rpe = 6.0 is inclusive (6.0 <= rpe <= 7.0)."""
        result = lt.estimate_lt2(hr_stable=True, rpe=6.0)
        assert result["is_lt2"] is True

    def test_lt2_boundary_rpe_7_is_true(self, lt):
        """rpe = 7.0 is inclusive."""
        result = lt.estimate_lt2(hr_stable=True, rpe=7.0)
        assert result["is_lt2"] is True

    def test_lt2_result_has_required_keys(self, lt):
        result = lt.estimate_lt2(True, 6.5)
        for key in ("is_lt2", "status_text", "hr_stable", "rpe"):
            assert key in result

    def test_lt2_status_text_reflects_result(self, lt):
        true_result = lt.estimate_lt2(True, 6.5)
        false_result = lt.estimate_lt2(False, 6.5)
        assert "TRUE" in true_result["status_text"]
        assert "FALSE" in false_result["status_text"]

    def test_lt2_stores_inputs(self, lt):
        result = lt.estimate_lt2(hr_stable=True, rpe=6.8)
        assert result["hr_stable"] is True
        assert result["rpe"] == 6.8

    # ── tempo_volume_decision ──────────────────────────────────────────────

    def test_tempo_volume_ok_when_lt2_true(self, lt):
        result = lt.tempo_volume_decision(True)
        assert result["ok"] is True

    def test_tempo_volume_downgrade_when_lt2_false(self, lt):
        result = lt.tempo_volume_decision(False)
        assert result["ok"] is False

    def test_tempo_volume_result_has_required_keys(self, lt):
        result = lt.tempo_volume_decision(True)
        assert "ok" in result
        assert "text" in result

    def test_tempo_volume_text_ok_contains_ok(self, lt):
        result = lt.tempo_volume_decision(True)
        assert "OK" in result["text"]

    def test_tempo_volume_text_downgrade_contains_downgrade(self, lt):
        result = lt.tempo_volume_decision(False)
        assert "DOWNGRADE" in result["text"]

    def test_tempo_volume_truthy_non_bool_works(self, lt):
        """tempo_volume_decision accepts any truthy value."""
        result = lt.tempo_volume_decision(1)
        assert result["ok"] is True

    def test_tempo_volume_falsy_non_bool_works(self, lt):
        result = lt.tempo_volume_decision(0)
        assert result["ok"] is False
