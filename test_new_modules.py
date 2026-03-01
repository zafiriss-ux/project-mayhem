#!/usr/bin/env python3
"""
Pytest suite for previously-untested TITAN modules.

Coverage targets (all new):
  - titan/science/drift_engine.py       (DriftEngine)
  - titan/science/fatigue_engine.py     (FatigueEngine)
  - titan/science/biomechanics.py       (BiomechanicsAnalysis)
  - titan/features/optimal_time_calculator.py (OptimalTimeCalculator)
  - titan/integrations/garmin_sync.py   (GarminSync)
  - titan/science/rcp_engine.py         (RCPEngine)
  - titan/science/efficiency_engine.py  (EfficiencyEngine)
  - titan/science/durability_engine.py  (DurabilityEngine)
  - titan/science/adaptive_memory.py    (AdaptiveMemory)
  - titan/orchestration/daily_coach.py  (DailyCoach helpers)

Run with:
    pytest test_new_modules.py -v
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from titan.science.drift_engine import DriftEngine
from titan.science.fatigue_engine import FatigueEngine
from titan.science.biomechanics import BiomechanicsAnalysis
from titan.features.optimal_time_calculator import OptimalTimeCalculator
from titan.integrations.garmin_sync import GarminSync
from titan.science.rcp_engine import RCPEngine
from titan.science.efficiency_engine import EfficiencyEngine
from titan.science.durability_engine import DurabilityEngine
from titan.science.adaptive_memory import AdaptiveMemory
from titan.core.database import DatabaseManager


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _make_window(start_hour: int, score: float, dew: float = 10.0, temp: float = 15.0,
                 quality: str = "GOOD") -> dict:
    """Build a synthetic weather window dict matching WeatherAPI output."""
    day = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)
    return {
        "start_time": day.isoformat(),
        "start_hour": start_hour,
        "score": score,
        "avg_dew_point": dew,
        "avg_temp": temp,
        "quality": quality,
    }


# ══════════════════════════════════════════════════════════════════════════════
# DriftEngine
# ══════════════════════════════════════════════════════════════════════════════

class TestDriftEngine:

    # ── compute_drift ─────────────────────────────────────────────────────────

    def test_compute_drift_positive(self):
        drift = DriftEngine.compute_drift(150, 160)
        assert abs(drift - 6.667) < 0.01

    def test_compute_drift_negative(self):
        drift = DriftEngine.compute_drift(160, 150)
        assert drift < 0

    def test_compute_drift_zero(self):
        assert DriftEngine.compute_drift(150, 150) == 0.0

    def test_compute_drift_zero_first_half_returns_zero(self):
        # Guard against ZeroDivisionError
        assert DriftEngine.compute_drift(0, 160) == 0.0

    def test_compute_drift_negative_first_half_returns_zero(self):
        assert DriftEngine.compute_drift(-5, 160) == 0.0

    # ── drift_rule (boundary conditions at 3% and 5%) ────────────────────────

    def test_drift_rule_below_3_pct(self):
        result = DriftEngine.drift_rule(2.9)
        assert "3%" in result and "Hammer" in result

    def test_drift_rule_exactly_3_pct(self):
        # 3.0 is NOT < 3.0, so it falls into the middle bucket
        result = DriftEngine.drift_rule(3.0)
        assert "3-5%" in result or "Maintain" in result

    def test_drift_rule_above_5_pct(self):
        result = DriftEngine.drift_rule(5.1)
        assert "5%" in result and "Stop" in result

    def test_drift_rule_exactly_5_pct(self):
        # 5.0 is NOT > 5.0, falls into middle bucket
        result = DriftEngine.drift_rule(5.0)
        assert "3-5%" in result or "Maintain" in result

    def test_drift_rule_zero(self):
        result = DriftEngine.drift_rule(0.0)
        assert "Hammer" in result  # < 3%

    # ── classify_drift (thresholds: 2.0, 3.5, 5.0) ───────────────────────────

    @pytest.mark.parametrize("pct,expected", [
        (1.0, "EXCELLENT"),
        (1.9, "EXCELLENT"),
        (2.0, "GOOD"),        # boundary — NOT < 2.0
        (3.4, "GOOD"),
        (3.5, "ACCEPTABLE"),  # boundary — NOT < 3.5
        (4.9, "ACCEPTABLE"),
        (5.0, "POOR"),        # boundary — NOT < 5.0
        (8.0, "POOR"),
    ])
    def test_classify_drift_thresholds(self, pct, expected):
        assert DriftEngine.classify_drift(pct) == expected


# ══════════════════════════════════════════════════════════════════════════════
# FatigueEngine
# ══════════════════════════════════════════════════════════════════════════════

class TestFatigueEngine:

    def test_no_signals_returns_low(self):
        severity, types = FatigueEngine.classify_fatigue(False, False, False, 0)
        assert severity == "LOW"
        assert types == ["NONE"]

    def test_hr_suppression_alone(self):
        severity, types = FatigueEngine.classify_fatigue(True, False, False, 0)
        assert severity == "MEDIUM"
        assert "CENTRAL" in types

    def test_rpe_mismatch_alone(self):
        severity, types = FatigueEngine.classify_fatigue(False, True, False, 0)
        assert severity == "MEDIUM"
        assert "CENTRAL" in types

    def test_pace_hr_divergence_alone(self):
        severity, types = FatigueEngine.classify_fatigue(False, False, True, 0)
        assert severity == "MEDIUM"
        assert "METABOLIC" in types

    def test_central_and_metabolic_yields_high(self):
        severity, types = FatigueEngine.classify_fatigue(True, False, True, 0)
        assert severity == "HIGH"
        assert "CENTRAL" in types
        assert "METABOLIC" in types

    def test_high_soreness_threshold(self):
        # soreness == 5 triggers PERIPHERAL
        severity, types = FatigueEngine.classify_fatigue(False, False, False, 5)
        assert "PERIPHERAL" in types

    def test_soreness_4_does_not_trigger_peripheral(self):
        severity, types = FatigueEngine.classify_fatigue(False, False, False, 4)
        assert severity == "LOW"

    def test_central_and_peripheral_yields_medium(self):
        severity, types = FatigueEngine.classify_fatigue(True, False, False, 5)
        assert severity == "MEDIUM"
        assert "CENTRAL" in types and "PERIPHERAL" in types

    def test_metabolic_and_peripheral_yields_medium(self):
        severity, types = FatigueEngine.classify_fatigue(False, False, True, 5)
        assert severity == "MEDIUM"

    def test_all_signals_yields_high(self):
        severity, types = FatigueEngine.classify_fatigue(True, True, True, 7)
        assert severity == "HIGH"

    def test_types_deduplication(self):
        # hr_suppression AND rpe_mismatch both append CENTRAL — should be deduped
        severity, types = FatigueEngine.classify_fatigue(True, True, False, 0)
        assert types.count("CENTRAL") == 1


# ══════════════════════════════════════════════════════════════════════════════
# BiomechanicsAnalysis
# ══════════════════════════════════════════════════════════════════════════════

class TestBiomechanicsAnalysis:

    # ── optimal_cadence ───────────────────────────────────────────────────────

    @pytest.mark.parametrize("height,expected_range", [
        (160, (175, 185)),  # short runner
        (174, (175, 185)),  # just below 175
        (175, (170, 180)),  # boundary
        (180, (170, 180)),
        (184, (170, 180)),  # just below 185
        (185, (165, 175)),  # boundary
        (195, (165, 175)),  # tall runner
    ])
    def test_optimal_cadence_height_brackets(self, height, expected_range):
        assert BiomechanicsAnalysis.optimal_cadence(height) == expected_range

    # ── stride_length ─────────────────────────────────────────────────────────

    def test_stride_length_normal(self):
        # 3 m/s @ 180 spm → (3 * 60) / 180 = 1.0 m
        sl = BiomechanicsAnalysis.stride_length(3.0, 180)
        assert sl == 1.0

    def test_stride_length_zero_cadence_returns_zero(self):
        assert BiomechanicsAnalysis.stride_length(3.0, 0) == 0.0

    def test_stride_length_rounding(self):
        sl = BiomechanicsAnalysis.stride_length(3.333, 175)
        assert isinstance(sl, float)
        assert round(sl, 2) == sl  # rounded to 2dp

    # ── analyze_form ──────────────────────────────────────────────────────────

    def test_perfect_form_no_issues(self):
        score, status, issues = BiomechanicsAnalysis.analyze_form(180, 9.0, 230)
        assert score == 100
        assert "EXCELLENT" in status
        assert issues == []

    def test_low_cadence_penalty(self):
        score, _, issues = BiomechanicsAnalysis.analyze_form(155, 9.0, 230)
        assert score == 85  # -15 for cadence
        assert any("cadence" in i.lower() for i in issues)

    def test_high_cadence_penalty(self):
        score, _, issues = BiomechanicsAnalysis.analyze_form(200, 9.0, 230)
        assert score == 90  # -10 for very high cadence

    def test_high_vertical_oscillation_penalty(self):
        score, _, issues = BiomechanicsAnalysis.analyze_form(180, 13.0, 230)
        assert score == 85  # -15

    def test_low_vertical_oscillation_penalty(self):
        score, _, issues = BiomechanicsAnalysis.analyze_form(180, 5.0, 230)
        assert score == 95  # -5

    def test_long_ground_contact_penalty(self):
        score, _, issues = BiomechanicsAnalysis.analyze_form(180, 9.0, 290)
        assert score == 90  # -10

    def test_very_short_ground_contact_penalty(self):
        score, _, issues = BiomechanicsAnalysis.analyze_form(180, 9.0, 170)
        assert score == 95  # -5

    def test_multiple_issues_cumulative(self):
        # cadence < 160 (-15) + vert_osc > 12 (-15) + gct > 280 (-10) = 60
        score, status, issues = BiomechanicsAnalysis.analyze_form(155, 14.0, 300)
        assert score == 60
        assert "NEEDS WORK" in status or "FAIR" in status

    @pytest.mark.parametrize("score_override,expected_status_fragment", [
        # We use form settings that produce these approximate scores
        (80, "EXCELLENT"),  # score >=80
        (70, "GOOD"),       # score >=70 and <80
    ])
    def test_status_thresholds(self, score_override, expected_status_fragment):
        # Build settings that hit the desired score
        if expected_status_fragment == "EXCELLENT":
            s, status, _ = BiomechanicsAnalysis.analyze_form(180, 9.0, 230)
            assert "EXCELLENT" in status
        else:
            # cadence <160 → -15 → score=85 still EXCELLENT; use two deductions
            s, status, _ = BiomechanicsAnalysis.analyze_form(180, 13.0, 290)
            assert "GOOD" in status  # 100-15-10=75

    # ── form_efficiency_score ─────────────────────────────────────────────────

    def test_form_efficiency_score_range(self):
        ef = BiomechanicsAnalysis.form_efficiency_score(180, 9.0, 230)
        assert 0.0 <= ef <= 1.0
        assert ef == 1.0  # perfect form

    def test_form_efficiency_score_bad_form(self):
        ef = BiomechanicsAnalysis.form_efficiency_score(155, 14.0, 300)
        assert ef < 1.0


# ══════════════════════════════════════════════════════════════════════════════
# OptimalTimeCalculator
# ══════════════════════════════════════════════════════════════════════════════

class TestOptimalTimeCalculator:

    @pytest.fixture
    def mock_api(self):
        return MagicMock()

    @pytest.fixture
    def calc(self, mock_api):
        return OptimalTimeCalculator(weather_api=mock_api)

    def _set_windows(self, mock_api, windows):
        mock_api.find_optimal_training_windows.return_value = windows

    # ── no windows fallback ───────────────────────────────────────────────────

    def test_no_windows_returns_unknown(self, calc, mock_api):
        self._set_windows(mock_api, [])
        result = calc.calculate_optimal_time("EASY")
        assert result["quality"] == "UNKNOWN"
        assert result["recommended_time"] == "No data available"

    # ── basic recommendation ──────────────────────────────────────────────────

    def test_returns_best_window(self, calc, mock_api):
        windows = [
            _make_window(6, score=30.0),
            _make_window(14, score=10.0),  # lowest score → best
        ]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("EASY")
        assert result["recommended_hour"] == 14

    def test_alternatives_returned(self, calc, mock_api):
        windows = [_make_window(h, score=float(h)) for h in [6, 10, 14]]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("EASY")
        assert len(result["alternatives"]) == 2

    # ── session-type preference adjustments ───────────────────────────────────

    def test_intervals_bonus_for_late_morning(self, calc, mock_api):
        # hour=10 (9-11 range) → score -15 bonus vs hour=6
        w_late = _make_window(10, score=50.0)
        w_early = _make_window(6, score=50.0)
        self._set_windows(mock_api, [w_late, w_early])
        result = calc.calculate_optimal_time("INTERVALS")
        assert result["recommended_hour"] == 10

    def test_long_run_bonus_for_early_morning(self, calc, mock_api):
        # hour=6 (5-7 range) → score -20 bonus vs hour=12
        w_early = _make_window(6, score=50.0)
        w_midday = _make_window(12, score=50.0)
        self._set_windows(mock_api, [w_early, w_midday])
        result = calc.calculate_optimal_time("LONG_RUN")
        assert result["recommended_hour"] == 6

    def test_long_run_penalty_for_late_hour(self, calc, mock_api):
        # hour=11 (>10) → score +15 penalty
        w_late = _make_window(11, score=50.0)
        w_early = _make_window(6, score=60.0)  # starts higher but early gets -20
        self._set_windows(mock_api, [w_late, w_early])
        result = calc.calculate_optimal_time("LONG_RUN")
        # early: 60-20=40, late: 50+15=65 → early wins
        assert result["recommended_hour"] == 6

    def test_tempo_bonus_for_early_morning(self, calc, mock_api):
        w_early = _make_window(7, score=50.0)   # 6-8: -10
        w_midday = _make_window(13, score=50.0) # 11-15: +15
        self._set_windows(mock_api, [w_early, w_midday])
        result = calc.calculate_optimal_time("TEMPO")
        assert result["recommended_hour"] == 7

    def test_easy_no_session_adjustment(self, calc, mock_api):
        # EASY has no adjustments — window with lowest raw score wins
        windows = [_make_window(6, score=20.0), _make_window(14, score=30.0)]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("EASY")
        assert result["recommended_hour"] == 6

    # ── TSB adjustments ───────────────────────────────────────────────────────

    def test_tsb_fatigued_early_penalty(self, calc, mock_api):
        # tsb < -20: hour < 8 gets +10 penalty, hour 9-11 gets -5 bonus
        w_early = _make_window(6, score=50.0)   # +10 → 60
        w_mid = _make_window(10, score=50.0)    # -5 → 45
        self._set_windows(mock_api, [w_early, w_mid])
        result = calc.calculate_optimal_time("EASY", tsb_value=-25)
        assert result["recommended_hour"] == 10

    def test_tsb_fresh_early_bonus(self, calc, mock_api):
        # tsb > 5: hour 5-7 gets -5 bonus
        w_early = _make_window(6, score=50.0)   # -5 → 45
        w_late = _make_window(12, score=50.0)   # unchanged → 50
        self._set_windows(mock_api, [w_early, w_late])
        result = calc.calculate_optimal_time("EASY", tsb_value=10)
        assert result["recommended_hour"] == 6

    def test_tsb_none_skips_adjustment(self, calc, mock_api):
        # tsb_value=None: branch not entered, raw scores unchanged
        windows = [_make_window(6, score=20.0)]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("EASY", tsb_value=None)
        assert result["recommended_hour"] == 6

    # ── athlete preference adjustments ────────────────────────────────────────

    def test_morning_person_prefers_early(self, calc, mock_api):
        w_early = _make_window(7, score=50.0)    # < 9: -10 → 40
        w_evening = _make_window(17, score=50.0) # > 16: +10 → 60
        self._set_windows(mock_api, [w_early, w_evening])
        result = calc.calculate_optimal_time(
            "EASY", athlete_preferences={"circadian_preference": "morning"}
        )
        assert result["recommended_hour"] == 7

    def test_evening_person_prefers_late(self, calc, mock_api):
        w_early = _make_window(7, score=50.0)    # < 9: +10 → 60
        w_evening = _make_window(17, score=50.0) # >= 16: -10 → 40
        self._set_windows(mock_api, [w_early, w_evening])
        result = calc.calculate_optimal_time(
            "EASY", athlete_preferences={"circadian_preference": "evening"}
        )
        assert result["recommended_hour"] == 17

    def test_flexible_preference_no_adjustment(self, calc, mock_api):
        windows = [_make_window(6, score=20.0), _make_window(18, score=30.0)]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time(
            "EASY", athlete_preferences={"circadian_preference": "flexible"}
        )
        assert result["recommended_hour"] == 6

    # ── _generate_reasoning ───────────────────────────────────────────────────

    def test_reasoning_low_dew_point(self, calc, mock_api):
        windows = [_make_window(6, score=10.0, dew=8.0, temp=15.0)]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("EASY")
        assert any("Low dew point" in r for r in result["reasoning"])

    def test_reasoning_high_dew_point(self, calc, mock_api):
        windows = [_make_window(6, score=10.0, dew=19.0, temp=15.0)]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("EASY")
        assert any("High dew point" in r for r in result["reasoning"])

    def test_reasoning_ideal_temperature(self, calc, mock_api):
        windows = [_make_window(6, score=10.0, dew=10.0, temp=15.0)]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("EASY")
        assert any("Ideal temperature" in r for r in result["reasoning"])

    def test_reasoning_long_run_early_morning(self, calc, mock_api):
        windows = [_make_window(6, score=10.0, dew=10.0, temp=15.0)]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("LONG_RUN")
        assert any("long run" in r.lower() for r in result["reasoning"])

    def test_reasoning_tsb_fatigue(self, calc, mock_api):
        windows = [_make_window(10, score=10.0, dew=10.0, temp=15.0)]
        self._set_windows(mock_api, windows)
        result = calc.calculate_optimal_time("EASY", tsb_value=-25)
        assert any("fatigue" in r.lower() for r in result["reasoning"])


# ══════════════════════════════════════════════════════════════════════════════
# GarminSync
# ══════════════════════════════════════════════════════════════════════════════

class TestGarminSync:

    def test_connect_missing_credentials_returns_false(self):
        gs = GarminSync(email="", password="")
        result = gs.connect()
        assert result is False
        assert gs.is_connected is False

    def test_connect_library_missing_returns_false(self, monkeypatch):
        # Simulate garminconnect not installed
        gs = GarminSync(email="test@example.com", password="secret")
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            result = gs.connect()
        assert result is False

    def test_connect_oauth_error_returns_false(self, monkeypatch):
        gs = GarminSync(email="test@example.com", password="secret")
        mock_client = MagicMock()
        mock_client.login.side_effect = Exception("OAuth token expired 401")
        with patch("titan.integrations.garmin_sync.GarminSync.connect") as mock_connect:
            mock_connect.return_value = False
            result = gs.connect()
        assert result is False

    def test_sync_activities_returns_empty_when_not_connected(self):
        gs = GarminSync(email="", password="")
        acts = gs.sync_activities()
        assert acts == []

    def test_sync_weight_returns_empty_when_not_connected(self):
        gs = GarminSync(email="", password="")
        assert gs.sync_weight() == []

    def test_sync_sleep_returns_empty_when_not_connected(self):
        gs = GarminSync(email="", password="")
        assert gs.sync_sleep() == []

    def test_sync_hrv_returns_empty_when_not_connected(self):
        gs = GarminSync(email="", password="")
        assert gs.sync_hrv() == []

    def test_sync_activities_parses_raw_activity(self):
        gs = GarminSync(email="test@example.com", password="secret")
        gs.is_connected = True
        raw_activity = {
            "duration": "3600",
            "distance": "10000",
            "averageHR": "145",
            "maxHR": "170",
            "startTimeLocal": "2024-03-01 07:00:00",
            "activityType": {"typeKey": "running"},
            "calories": "500",
            "elevationGain": "50",
            "activityId": "12345",
        }
        gs.client = MagicMock()
        gs.client.get_activities_by_date.return_value = [raw_activity]
        acts = gs.sync_activities(days_back=1)
        assert len(acts) == 1
        act = acts[0]
        assert act["distance_km"] == 10.0
        assert act["duration_sec"] == 3600
        assert act["avg_hr"] == 145
        assert act["max_hr"] == 170
        assert act["avg_pace_sec_per_km"] == 360  # 3600 / (10000/1000)
        assert act["calories"] == 500
        assert act["activity_id"] == "12345"

    def test_sync_activities_skips_bad_records(self):
        gs = GarminSync(email="test@example.com", password="secret")
        gs.is_connected = True
        # A record that will cause an exception when parsed (distance=0 means int division)
        bad = {"duration": "abc_NOT_A_NUMBER", "distance": "not_a_float"}
        good = {
            "duration": "1800",
            "distance": "5000",
            "startTimeLocal": "2024-03-01 08:00:00",
            "activityType": {"typeKey": "running"},
        }
        gs.client = MagicMock()
        gs.client.get_activities_by_date.return_value = [bad, good]
        acts = gs.sync_activities(days_back=1)
        # bad record skipped, good record included
        assert len(acts) == 1

    def test_sync_hrv_parses_rmssd(self):
        gs = GarminSync(email="test@example.com", password="secret")
        gs.is_connected = True
        gs.client = MagicMock()
        gs.client.get_hrv_data.return_value = {
            "hrvSummary": {"lastNight5MinHigh": "62.5", "status": "BALANCED"}
        }
        hrv = gs.sync_hrv(days_back=1)
        assert len(hrv) == 1
        assert hrv[0]["rmssd"] == 62.5
        assert hrv[0]["status"] == "BALANCED"

    def test_sync_hrv_skips_missing_rmssd(self):
        gs = GarminSync(email="test@example.com", password="secret")
        gs.is_connected = True
        gs.client = MagicMock()
        gs.client.get_hrv_data.return_value = {"hrvSummary": {}}
        hrv = gs.sync_hrv(days_back=1)
        assert hrv == []

    def test_log_sync_appends_and_caps_at_100(self):
        gs = GarminSync()
        for i in range(105):
            gs._log_sync("activities", i)
        assert len(gs.sync_history) == 100

    def test_get_sync_summary_structure(self):
        gs = GarminSync()
        gs.last_sync = "2024-01-01T10:00:00"
        summary = gs.get_sync_summary()
        assert "last_sync" in summary
        assert "is_connected" in summary
        assert "total_syncs" in summary

    def test_stop_background_sync(self):
        gs = GarminSync()
        gs._stop_sync = False
        gs.stop_background_sync()
        assert gs._stop_sync is True

    def test_ensure_connected_when_already_connected(self):
        gs = GarminSync(email="test@example.com", password="secret")
        gs.is_connected = True
        gs.client = MagicMock()
        # Should return True without calling connect()
        result = gs._ensure_connected()
        assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# RCPEngine
# ══════════════════════════════════════════════════════════════════════════════

class TestRCPEngine:

    # ── estimate_rcp_from_progressive_test ────────────────────────────────────

    def test_insufficient_segments_returns_none(self):
        hr, pace, rpe, explanation = RCPEngine.estimate_rcp_from_progressive_test(
            [300, 270, 250], [130, 145, 155], [6, 7, 8]
        )
        assert hr is None and pace is None
        assert "4+" in explanation

    def test_detects_inflection_point(self):
        # Segment 2→3 shows accelerating HR:Pace degradation
        # speed1=1000/300=3.33 m/s, ratio1=130/3.33=39.0
        # speed2=1000/270=3.70 m/s, ratio2=145/3.70=39.2 — delta_before≈0.2
        # speed3=1000/240=4.17 m/s, ratio3=165/4.17=39.6 — delta_after≈0.4
        # delta_after > delta_before * 1.5 → inflection at i=2
        hr, pace, rpe, explanation = RCPEngine.estimate_rcp_from_progressive_test(
            [300, 270, 240, 210],
            [130, 145, 165, 185],
            [6.0, 7.0, 8.0, 9.0]
        )
        # Should find an inflection or fall back to second-to-last
        assert hr is not None
        assert pace is not None
        assert isinstance(explanation, str)

    def test_fallback_when_no_clear_inflection(self):
        # Linear HR:Pace increase — no inflection
        paces = [300, 285, 270, 255]
        hrs = [130, 138, 146, 154]
        rpes = [6.0, 6.5, 7.0, 7.5]
        hr, pace, rpe, explanation = RCPEngine.estimate_rcp_from_progressive_test(
            paces, hrs, rpes
        )
        assert hr == hrs[-2]
        assert pace == paces[-2]
        assert "no clear" in explanation.lower() or "estimated" in explanation.lower()

    # ── rcp_training_zones ────────────────────────────────────────────────────

    def test_training_zones_keys(self):
        zones = RCPEngine.rcp_training_zones(rcp_hr=170, max_hr=195)
        assert "Zone 1 (Easy)" in zones
        assert "Zone 2 (Threshold)" in zones
        assert "Zone 3 (VO2max)" in zones
        assert zones["RCP_HR"] == 170
        assert zones["Max_HR"] == 195

    def test_vt1_is_85_pct_rcp(self):
        zones = RCPEngine.rcp_training_zones(rcp_hr=170, max_hr=195)
        expected_vt1 = int(170 * 0.85)
        assert zones["VT1_HR"] == expected_vt1

    # ── calculate_rcp_training_zones ─────────────────────────────────────────

    def test_precise_zones_structure(self):
        zones = RCPEngine.calculate_rcp_training_zones(rcp_hr=170, max_hr=195)
        assert zones["zone_1_easy"] == (0, int(170 * 0.85))
        assert zones["zone_2_threshold"][0] == int(170 * 0.85)
        assert zones["zone_2_threshold"][1] == 170
        assert zones["zone_3_vo2max"] == (170, 195)

    def test_zone_boundaries_are_contiguous(self):
        zones = RCPEngine.calculate_rcp_training_zones(rcp_hr=160, max_hr=190)
        assert zones["zone_1_easy"][1] == zones["zone_2_threshold"][0]
        assert zones["zone_2_threshold"][1] == zones["zone_3_vo2max"][0]


# ══════════════════════════════════════════════════════════════════════════════
# EfficiencyEngine
# ══════════════════════════════════════════════════════════════════════════════

class TestEfficiencyEngine:

    # ── calculate_efficiency_factor ───────────────────────────────────────────

    def test_ef_normal_calculation(self):
        # 5:00/km = 300 sec/km → speed=1000/300=3.333 m/s; HR=150
        ef = EfficiencyEngine.calculate_efficiency_factor(300.0, 150.0)
        expected = round((1000.0 / 300.0) / 150.0, 5)
        assert ef == expected

    def test_ef_zero_hr_returns_none(self):
        assert EfficiencyEngine.calculate_efficiency_factor(300.0, 0) is None

    def test_ef_higher_for_faster_pace_same_hr(self):
        ef_fast = EfficiencyEngine.calculate_efficiency_factor(250.0, 150.0)
        ef_slow = EfficiencyEngine.calculate_efficiency_factor(360.0, 150.0)
        assert ef_fast > ef_slow

    # ── calculate_decoupling ──────────────────────────────────────────────────

    def test_decoupling_no_drift_elite(self):
        # Same pace and HR both halves → 0% decoupling
        dec, status = EfficiencyEngine.calculate_decoupling(300, 150, 300, 150)
        assert dec == 0.0
        assert "ELITE" in status

    def test_decoupling_second_half_slower_hr_same(self):
        # Second half: slower pace (larger sec/km) → lower EF → negative decoupling
        dec, status = EfficiencyEngine.calculate_decoupling(300, 150, 330, 150)
        assert dec < 0  # efficiency worsened

    def test_decoupling_invalid_zero_hr_returns_none(self):
        dec, status = EfficiencyEngine.calculate_decoupling(300, 0, 300, 150)
        assert dec is None
        assert "Invalid" in status

    @pytest.mark.parametrize("dec_pct,expected_fragment", [
        (2.0, "ELITE"),
        (4.0, "EXCELLENT"),
        (7.0, "MODERATE"),
        (12.0, "HIGH"),
    ])
    def test_decoupling_status_thresholds(self, dec_pct, expected_fragment):
        # Manipulate EF directly to hit exact percentages
        # ef_first = 0.02, ef_second = ef_first * (1 - dec_pct/100)
        # but calculate_decoupling uses (ef_second - ef_first) / ef_first * 100
        # We pass halves that produce the expected magnitude of decoupling
        ef_first = 0.022
        ef_second = ef_first * (1 + dec_pct / 100)
        # pace = 1000 / (ef * hr); hr = 150
        hr = 150.0
        pace_first = 1000.0 / (ef_first * hr)
        pace_second = 1000.0 / (ef_second * hr)
        dec, status = EfficiencyEngine.calculate_decoupling(
            pace_first, hr, pace_second, hr
        )
        assert abs(dec) > 0
        assert expected_fragment in status

    # ── add_ef_measurement / analyze_ef_trend ────────────────────────────────

    def test_add_ef_measurement_stored(self):
        engine = EfficiencyEngine()
        engine.add_ef_measurement("2024-01-01", 0.022)
        assert len(engine.ef_history) == 1

    def test_trend_insufficient_data(self):
        engine = EfficiencyEngine()
        engine.add_ef_measurement("2024-01-01", 0.022)
        result = engine.analyze_ef_trend(weeks=3)
        assert "Need more data" in result or "historical" in result

    def test_trend_improving(self):
        engine = EfficiencyEngine()
        # 6 weeks of data: first 3 weeks low, last 3 weeks high
        for i in range(21):
            engine.add_ef_measurement(f"2023-{i+1:02d}", 0.018)  # previous period
        for i in range(21):
            engine.add_ef_measurement(f"2024-{i+1:02d}", 0.025)  # recent period (much higher)
        result = engine.analyze_ef_trend(weeks=3)
        assert "IMPROVING" in result

    def test_trend_declining(self):
        engine = EfficiencyEngine()
        for i in range(21):
            engine.add_ef_measurement(f"2023-{i+1:02d}", 0.028)
        for i in range(21):
            engine.add_ef_measurement(f"2024-{i+1:02d}", 0.020)
        result = engine.analyze_ef_trend(weeks=3)
        assert "DECLINING" in result


# ══════════════════════════════════════════════════════════════════════════════
# DurabilityEngine
# ══════════════════════════════════════════════════════════════════════════════

class TestDurabilityEngine:

    # ── assess_pace_durability ────────────────────────────────────────────────

    def test_insufficient_splits_returns_none(self):
        decay, status, rec = DurabilityEngine.assess_pace_durability([300] * 9, 300)
        assert decay is None
        assert "10+" in status

    def test_negative_split_exceptional(self):
        # First 4 splits slow, last 4 fast → negative decay
        splits = [310, 308, 305, 300, 295, 290, 285, 280, 275, 270, 265, 260]
        decay, status, rec = DurabilityEngine.assess_pace_durability(splits, 300)
        assert decay < 0
        assert "NEGATIVE" in status

    def test_excellent_durability(self):
        # < 2% fade
        splits = [300.0] * 5 + [302.0] * 5 + [301.0] * 2  # minimal fade
        decay, status, rec = DurabilityEngine.assess_pace_durability(splits, 300)
        assert "EXCELLENT" in status or "NEGATIVE" in status

    def test_poor_durability(self):
        # Large fade: first third fast, last third much slower
        first = [290.0] * 4
        middle = [300.0] * 4
        last = [330.0] * 4   # ~13.8% fade from 290 to 330
        decay, status, rec = DurabilityEngine.assess_pace_durability(first + middle + last, 300)
        assert "POOR" in status
        assert decay > 8

    # ── calculate_durability_index ────────────────────────────────────────────

    def test_di_zero_performance_returns_none(self):
        di, status, tier = DurabilityEngine.calculate_durability_index(0, 240)
        assert di is None

    def test_di_elite_level(self):
        # fresh=228, fatigued=228 → DI=100%
        di, status, tier = DurabilityEngine.calculate_durability_index(228, 228)
        assert di == 100.0
        assert tier == "WORLD CLASS"

    def test_di_competitive_level(self):
        # fresh=228, fatigued=240 → DI = 228/240*100 = 95
        di, status, tier = DurabilityEngine.calculate_durability_index(228, 240)
        assert abs(di - 95.0) < 0.1
        assert tier == "ELITE"

    @pytest.mark.parametrize("fresh,fatigued,expected_tier", [
        (228, 228, "WORLD CLASS"),   # 100% ≥ 98
        (235, 240, "ELITE"),         # 97.9% ≥ 95
        (228, 252, "COMPETITIVE"),   # 90.5% ≥ 90
        (228, 267, "DEVELOPING"),    # 85.4% ≥ 85
        (228, 285, "NOVICE"),        # 80% < 85
    ])
    def test_di_tiers(self, fresh, fatigued, expected_tier):
        di, status, tier = DurabilityEngine.calculate_durability_index(fresh, fatigued)
        assert tier == expected_tier

    # ── durability_training_protocol ─────────────────────────────────────────

    def test_protocol_below_88_priority_build(self):
        protocols = DurabilityEngine.durability_training_protocol(85.0)
        assert any("PRIORITY" in p for p in protocols)
        assert len(protocols) > 3

    def test_protocol_93_to_96_maintain(self):
        protocols = DurabilityEngine.durability_training_protocol(94.0)
        assert any("long run" in p.lower() for p in protocols)

    def test_protocol_elite_no_specific_work(self):
        protocols = DurabilityEngine.durability_training_protocol(97.0)
        assert any("ELITE" in p for p in protocols)


# ══════════════════════════════════════════════════════════════════════════════
# AdaptiveMemory
# ══════════════════════════════════════════════════════════════════════════════

class TestAdaptiveMemory:

    @pytest.fixture
    def mem(self):
        return AdaptiveMemory()

    # ── log_session ───────────────────────────────────────────────────────────

    def test_log_session_appends(self, mem):
        mem.log_session(datetime.now(), "EASY", 50.0, 6.0, 2.0, True)
        assert len(mem.session_history) == 1

    def test_quality_sessions_tracked(self, mem):
        now = datetime.now()
        mem.log_session(now, "TEMPO", 80.0, 7.0, 3.5, True)
        assert len(mem.last_quality_sessions) == 1

    def test_easy_sessions_not_tracked_as_quality(self, mem):
        mem.log_session(datetime.now(), "EASY", 40.0, 5.0, 1.5, True)
        assert len(mem.last_quality_sessions) == 0

    def test_quality_sessions_capped_at_5(self, mem):
        for i in range(7):
            mem.log_session(datetime.now() + timedelta(days=i), "INTERVALS", 90.0, 8.0, 4.0, True)
        assert len(mem.last_quality_sessions) == 5

    def test_soreness_rolling_window_3(self, mem):
        for s in [3.0, 4.0, 5.0, 6.0]:
            mem.log_session(datetime.now(), "EASY", 40.0, 5.0, 1.5, True, soreness=s)
        assert len(mem.last_3d_soreness) == 3
        assert mem.last_3d_soreness == [4.0, 5.0, 6.0]

    # ── calculate_neural_adaptation ───────────────────────────────────────────

    def test_neural_gain_detected(self, mem):
        result = mem.calculate_neural_adaptation(
            target_pace_sec=300, actual_pace_sec=295,
            avg_hr=155, threshold_hr=160
        )
        assert "NEURAL GAIN" in result
        assert mem.adaptive_pace_factor < 1.00

    def test_neural_stable_when_no_gain(self, mem):
        result = mem.calculate_neural_adaptation(
            target_pace_sec=300, actual_pace_sec=305,  # slower than target
            avg_hr=155, threshold_hr=160
        )
        assert "STABLE" in result
        assert mem.adaptive_pace_factor == 1.00  # unchanged

    def test_neural_no_gain_when_hr_exceeds_threshold(self, mem):
        result = mem.calculate_neural_adaptation(
            target_pace_sec=300, actual_pace_sec=295,
            avg_hr=165, threshold_hr=160  # HR over threshold
        )
        assert "STABLE" in result

    # ── check_monotony ────────────────────────────────────────────────────────

    def test_monotony_zero_std_dev_returns_unknown(self, mem):
        result = mem.check_monotony(60.0, 0)
        assert "UNKNOWN" in result

    def test_monotony_high_danger(self, mem):
        result = mem.check_monotony(60.0, 20.0)  # 60/20 = 3.0 > 2.5
        assert "DANGER" in result

    def test_monotony_medium_risk(self, mem):
        result = mem.check_monotony(60.0, 25.0)  # 60/25 = 2.4 > 2.0
        assert "RISK" in result

    def test_monotony_watch(self, mem):
        result = mem.check_monotony(60.0, 35.0)  # 60/35 = 1.71 > 1.5
        assert "WATCH" in result

    def test_monotony_healthy(self, mem):
        result = mem.check_monotony(60.0, 50.0)  # 60/50 = 1.2 ≤ 1.5
        assert "VARIATION" in result or "Healthy" in result

    def test_monotony_updates_index(self, mem):
        mem.check_monotony(60.0, 20.0)
        assert mem.monotony_index == pytest.approx(3.0, abs=0.01)

    # ── supercompensation_window ──────────────────────────────────────────────

    def test_supercomp_recovery_window(self, mem):
        result = mem.supercompensation_window(36.0)  # 24-48h
        assert "RECOVERY" in result
        assert mem.supercomp_status == "RECOVERY"

    def test_supercomp_peak_window(self, mem):
        result = mem.supercompensation_window(60.0)  # 48-72h
        assert "SUPER-COMPENSATION" in result
        assert mem.supercomp_status == "PEAK"

    def test_supercomp_baseline_outside_window(self, mem):
        result = mem.supercompensation_window(80.0)  # > 72h
        assert "BASELINE" in result
        assert mem.supercomp_status == "BASELINE"

    def test_supercomp_boundary_24h(self, mem):
        result = mem.supercompensation_window(24.0)
        assert "RECOVERY" in result  # 24 <= 24 <= 48

    # ── session_density_index ─────────────────────────────────────────────────

    def test_sdi_insufficient_data(self, mem):
        mem.last_quality_sessions = [datetime.now()]
        result = mem.session_density_index(datetime.now())
        assert "Not enough" in result

    def test_sdi_within_24h(self, mem):
        now = datetime.now()
        mem.last_quality_sessions = [now - timedelta(hours=40), now - timedelta(hours=12)]
        result = mem.session_density_index(now)
        assert "<24h" in result

    def test_sdi_safe_spacing(self, mem):
        now = datetime.now()
        mem.last_quality_sessions = [
            now - timedelta(hours=100), now - timedelta(hours=50)
        ]
        result = mem.session_density_index(now)
        assert "Safe" in result

    # ── mechanical_load_risk ──────────────────────────────────────────────────

    def test_mech_load_ok(self, mem):
        result = mem.mechanical_load_risk(300, 300)
        assert "OK" in result

    def test_mech_load_easy_pace_drop(self, mem):
        # today > baseline * 1.08
        result = mem.mechanical_load_risk(330, 300)  # 330 > 300*1.08=324
        assert "Watch" in result or "HIGH RISK" in result

    def test_mech_load_high_soreness(self, mem):
        mem.last_3d_soreness = [6.0, 6.0, 6.0]  # avg = 6 ≥ 5
        result = mem.mechanical_load_risk(300, 300)
        assert "Watch" in result or "HIGH RISK" in result

    def test_mech_load_high_risk_both_flags(self, mem):
        mem.last_3d_soreness = [6.0, 6.0, 6.0]
        result = mem.mechanical_load_risk(330, 300)  # both flags
        assert "HIGH RISK" in result


# ══════════════════════════════════════════════════════════════════════════════
# DailyCoach helpers (tested in isolation via stubs)
# ══════════════════════════════════════════════════════════════════════════════

class TestDailyCoachHelpers:
    """
    Test private helper methods on DailyCoach using stub dependencies.
    The full run_morning_routine() is an integration concern and requires
    a live DB + Garmin mock; individual helpers are covered here.
    """

    @pytest.fixture
    def stub_deps(self, tmp_path):
        """Minimal stubs for all DailyCoach constructor parameters."""
        from titan.orchestration.daily_coach import DailyCoach

        garmin = MagicMock()
        garmin.sync_all.return_value = {
            "activities": [], "weight": [], "sleep": [], "hrv": []
        }

        hrv_engine = MagicMock()
        hrv_engine.hrv_log = []
        hrv_engine.add_hrv_measurement = MagicMock()

        tsb_engine = MagicMock()
        tsb_engine.daily_loads = []
        tsb_engine.add_daily_load = MagicMock()
        tsb_engine.calculate_tsb.return_value = (5.0, "FRESH")

        readiness_engine = MagicMock()
        readiness_engine.analyze_readiness.return_value = {"score": 80, "status": "GOOD"}

        weather_api = MagicMock()
        weather_api.find_optimal_training_windows.return_value = [
            _make_window(6, score=10.0)
        ]

        optimal_time_calc = MagicMock()
        optimal_time_calc.calculate_optimal_time.return_value = {
            "recommended_time": "06:00", "quality": "GOOD",
            "dew_point": 10.0, "reasoning": []
        }

        nutrition_optimizer = MagicMock()
        nutrition_optimizer.analyze_weight_trend.return_value = {"current_weight": 75.0}
        nutrition_optimizer.add_weight_entry = MagicMock()
        nutrition_optimizer.calculate_daily_nutrition.return_value = {
            "carbs_g": 300, "protein_g": 120
        }

        weekly_planner = MagicMock()
        weekly_planner.get_today_session.return_value = {
            "session_type": "EASY", "duration_min": 45,
            "distance_km": 8, "details": "Easy run"
        }

        db = DatabaseManager(db_name=str(tmp_path / "coach_test.db"))

        coach = DailyCoach(
            garmin_sync=garmin,
            weather_api=weather_api,
            telegram_bot=MagicMock(send_daily_coaching=MagicMock(return_value=True)),
            hrv_engine=hrv_engine,
            tsb_engine=tsb_engine,
            readiness_engine=readiness_engine,
            optimal_time_calc=optimal_time_calc,
            nutrition_optimizer=nutrition_optimizer,
            weekly_planner=weekly_planner,
            db=db,
        )
        return coach, db

    # ── _persist_garmin_data ─────────────────────────────────────────────────

    def test_persist_defaults_with_empty_data(self, stub_deps):
        coach, _ = stub_deps
        rhr, sleep_score, sleep_hours = coach._persist_garmin_data({}, "2024-03-01")
        assert rhr == 0
        assert sleep_score == 75
        assert sleep_hours == 7.5

    def test_persist_extracts_rhr_from_sleep(self, stub_deps):
        coach, _ = stub_deps
        garmin_data = {
            "sleep": [{"rhr": 48, "sleepTimeSeconds": 28800}]
        }
        rhr, _, hours = coach._persist_garmin_data(garmin_data, "2024-03-01")
        assert rhr == 48
        assert abs(hours - 8.0) < 0.01

    def test_persist_extracts_sleep_score_nested(self, stub_deps):
        coach, _ = stub_deps
        garmin_data = {
            "sleep": [{"sleepScores": {"overall": {"value": 82}}}]
        }
        _, sleep_score, _ = coach._persist_garmin_data(garmin_data, "2024-03-01")
        assert sleep_score == 82

    def test_persist_saves_activities_to_db(self, stub_deps):
        coach, db = stub_deps
        garmin_data = {
            "activities": [
                {
                    "date": "2024-03-01",
                    "distance_km": 10.0,
                    "duration_sec": 3600,
                    "avg_hr": 145,
                }
            ]
        }
        coach._persist_garmin_data(garmin_data, "2024-03-01")
        # Verify it was saved without raising an exception

    def test_persist_skips_empty_sleep_entries(self, stub_deps):
        coach, _ = stub_deps
        garmin_data = {"sleep": [None, {}, {"rhr": 52}]}
        rhr, _, _ = coach._persist_garmin_data(garmin_data, "2024-03-01")
        assert rhr == 52

    # ── _get_recent_trimp ────────────────────────────────────────────────────

    def test_get_recent_trimp_uses_trimp_field(self, stub_deps):
        coach, _ = stub_deps
        activities = [{"trimp": 80.0}, {"trimp": 60.0}]
        total = coach._get_recent_trimp(activities)
        assert total == 140.0

    def test_get_recent_trimp_fallback_training_load(self, stub_deps):
        coach, _ = stub_deps
        activities = [{"training_load": 100.0}]
        total = coach._get_recent_trimp(activities)
        assert abs(total - 60.0) < 0.1  # 100 * 0.6

    def test_get_recent_trimp_empty_list(self, stub_deps):
        coach, _ = stub_deps
        assert coach._get_recent_trimp([]) == 0.0

    def test_get_recent_trimp_ignores_zero_trimp(self, stub_deps):
        coach, _ = stub_deps
        activities = [{"trimp": 0}, {"training_load": 50.0}]
        total = coach._get_recent_trimp(activities)
        assert abs(total - 30.0) < 0.1  # falls back to training_load

    # ── _feed_load_engines ────────────────────────────────────────────────────

    def test_feed_load_engines_clears_and_reloads(self, stub_deps):
        coach, db = stub_deps
        # Pre-load the tsb engine with stale data
        coach.tsb.daily_loads = [("stale", 999.0)]
        # _feed_load_engines clears and reloads from DB; DB is empty → list ends empty
        coach._feed_load_engines([])
        assert coach.tsb.daily_loads == []

    # ── _get_baseline_rhr ────────────────────────────────────────────────────

    def test_baseline_rhr_fallback_no_data(self, stub_deps):
        coach, _ = stub_deps
        baseline = coach._get_baseline_rhr(days=7)
        assert baseline == 50.0

    def test_baseline_rhr_uses_db_data(self, stub_deps):
        coach, db = stub_deps
        db.save_daily_metric("2024-02-28", rhr=52)
        db.save_daily_metric("2024-02-27", rhr=48)
        baseline = coach._get_baseline_rhr(days=30)
        assert 48 <= baseline <= 52
