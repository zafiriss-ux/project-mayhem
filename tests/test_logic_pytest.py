#!/usr/bin/env python3
"""
Pytest migration of test_titan_logic.py

Replaces the standalone ``if __name__ == "__main__"`` runner so these tests
are visible to coverage reporting and CI.  Also adds dedicated test classes
for ACWREngine, ReadinessEngine, TRIMPEngine, and NutritionOptimizer that
were previously only exercised by the standalone script (invisible to pytest
--cov) or not at all.

Run with:
    pytest tests/test_logic_pytest.py -v
    pytest tests/test_logic_pytest.py -v --cov=titan --cov-report=term-missing
"""

import os
import sys
from pathlib import Path

import pytest

# ── env stub (must happen before any titan import) ───────────────────────────
os.environ.setdefault("GARMIN_EMAIL",        "test@example.com")
os.environ.setdefault("GARMIN_PASSWORD",     "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN",  "1234567890:TEST")
os.environ.setdefault("TELEGRAM_CHAT_ID",    "12345")
os.environ.setdefault("WEATHER_API_KEY",     "test")
os.environ.setdefault("WEATHER_LOCATION",    "Athens,GR")

sys.path.insert(0, str(Path(__file__).parent.parent))


# ══════════════════════════════════════════════════════════════════════════════
# 1. HRV ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TestHRVEnginePytest:
    """Pytest port of test_titan_logic.test_hrv()."""

    @pytest.fixture
    def engine(self):
        from titan.science.hrv_engine import HRVGuidedEngine
        return HRVGuidedEngine()

    @pytest.fixture
    def loaded_engine(self, engine):
        for i, val in enumerate([55, 58, 60, 57, 62, 61, 63, 67]):
            engine.add_hrv_measurement(f"2026-02-{10 + i:02d}", val)
        return engine

    def test_empty_log_latest_hrv_zero(self, engine):
        assert engine.get_hrv_summary()["latest_hrv"] == 0.0

    def test_empty_log_baseline_zero(self, engine):
        assert engine.get_hrv_summary()["baseline"] == 0.0

    def test_latest_hrv_correct_after_data(self, loaded_engine):
        assert loaded_engine.get_hrv_summary()["latest_hrv"] == 67.0

    def test_baseline_positive_with_8_points(self, loaded_engine):
        assert loaded_engine.get_hrv_summary()["baseline"] > 0

    def test_data_points_count(self, loaded_engine):
        assert loaded_engine.get_hrv_summary()["data_points"] == 8

    def test_high_hrv_keeps_quality_session(self, loaded_engine):
        rec, _, _ = loaded_engine.get_training_recommendation(68, "INTERVALS")
        assert rec == "INTERVALS"

    def test_very_low_hrv_downgrades(self, loaded_engine):
        rec, _, _ = loaded_engine.get_training_recommendation(30, "INTERVALS")
        assert rec in ("REST", "EASY")


# ══════════════════════════════════════════════════════════════════════════════
# 2. READINESS ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TestReadinessEnginePytest:
    """
    Dedicated pytest class for ReadinessEngine.analyze_readiness().

    Previously only tested in the standalone test_titan_logic.py script,
    making it invisible to coverage reporting.
    """

    @staticmethod
    def _analyze(**kwargs):
        from titan.science.readiness_engine import ReadinessEngine
        return ReadinessEngine.analyze_readiness(**kwargs)

    _GOOD = {
        "today_hrv": 62,
        "baseline_hrv": 60,
        "today_rhr": 47,
        "baseline_rhr": 48,
        "sleep_score": 85,
        "soreness": 2,
    }
    _BAD = {
        "today_hrv": 50,
        "baseline_hrv": 62,
        "today_rhr": 55,
        "baseline_rhr": 48,
        "sleep_score": 40,
        "soreness": 4,
    }

    def test_good_night_score_above_80(self):
        assert self._analyze(**self._GOOD)["score"] > 80

    def test_bad_night_lower_than_good(self):
        assert self._analyze(**self._BAD)["score"] < self._analyze(**self._GOOD)["score"]

    def test_bad_night_not_excellent(self):
        assert "EXCELLENT" not in self._analyze(**self._BAD)["status"]

    def test_score_clamped_0_to_100(self):
        r = self._analyze(**self._GOOD)
        assert 0 <= r["score"] <= 100

    def test_perfect_conditions_excellent(self):
        r = self._analyze(today_hrv=70, baseline_hrv=55, today_rhr=44,
                          baseline_rhr=48, sleep_score=95, soreness=0)
        assert r["score"] >= 85

    def test_extreme_soreness_lowers_score(self):
        high_pain = self._analyze(today_hrv=60, baseline_hrv=60, today_rhr=48,
                                  baseline_rhr=48, sleep_score=80, soreness=9)
        low_pain  = self._analyze(today_hrv=60, baseline_hrv=60, today_rhr=48,
                                  baseline_rhr=48, sleep_score=80, soreness=1)
        assert high_pain["score"] < low_pain["score"]

    def test_elevated_rhr_lowers_score(self):
        normal = self._analyze(today_hrv=60, baseline_hrv=60, today_rhr=48,
                               baseline_rhr=48, sleep_score=80, soreness=2)
        elevated = self._analyze(today_hrv=60, baseline_hrv=60, today_rhr=56,
                                 baseline_rhr=48, sleep_score=80, soreness=2)
        assert elevated["score"] < normal["score"]

    def test_result_has_required_keys(self):
        r = self._analyze(**self._GOOD)
        for k in ("score", "status", "hrv_contribution", "rhr_contribution",
                  "sleep_contribution", "soreness_impact"):
            assert k in r, f"Missing key: {k}"

    def test_sleep_score_excellent_with_bonus(self):
        """sleep ≥ 85 gives +5 bonus and pushes status to EXCELLENT."""
        r = self._analyze(today_hrv=60, baseline_hrv=60, today_rhr=48,
                          baseline_rhr=48, sleep_score=95, soreness=1)
        assert "EXCELLENT" in r["status"]

    def test_poor_sleep_and_suppressed_hrv_gives_good_or_lower(self):
        """Sleep fair + HRV below baseline → score ≤ 84 → at most GOOD."""
        r = self._analyze(today_hrv=50, baseline_hrv=60, today_rhr=48,
                          baseline_rhr=48, sleep_score=55, soreness=1)
        # Score = 100 - 10(HRV) - 8(sleep<70) = 82 → GOOD
        assert r["score"] <= 84
        assert "GOOD" in r["status"] or "FAIR" in r["status"] or "POOR" in r["status"]

    def test_hrv_above_baseline_bonus(self):
        """HRV 12 points above baseline should push score above 100-clamp boundary."""
        boosted = self._analyze(today_hrv=72, baseline_hrv=60, today_rhr=48,
                                baseline_rhr=48, sleep_score=85, soreness=0)
        assert boosted["score"] == 100  # clamped at 100 after +10 HRV bonus + +5 sleep

    def test_hrv_far_below_baseline_penalty(self):
        suppressed = self._analyze(today_hrv=40, baseline_hrv=60, today_rhr=48,
                                   baseline_rhr=48, sleep_score=80, soreness=2)
        # -20 HRV penalty → score ≤ 80
        assert suppressed["score"] <= 80


# ══════════════════════════════════════════════════════════════════════════════
# 3. LACTATE LOGIC
# ══════════════════════════════════════════════════════════════════════════════

class TestLactateLogicPytest:
    """Pytest port of test_titan_logic.test_lactate()."""

    @pytest.fixture(autouse=True)
    def _ll(self):
        from titan.science.lactate_logic import LactateLogic
        self.ll = LactateLogic

    def test_lt1_detected_at_low_hr_drift(self):
        assert self.ll.estimate_lt1(75.0, 2.5)["is_lt1"] is True

    def test_lt1_result_has_is_lt1_key(self):
        assert "is_lt1" in self.ll.estimate_lt1(75.0, 2.5)

    def test_lt1_not_detected_at_high_hr(self):
        assert self.ll.estimate_lt1(82.0, 4.0)["is_lt1"] is False

    def test_lt2_detected_stable_hr_rpe_threshold(self):
        assert self.ll.estimate_lt2(hr_stable=True, rpe=6.5)["is_lt2"] is True

    def test_tempo_volume_decision_true_is_ok(self):
        r = self.ll.tempo_volume_decision(True)
        assert "ok" in r and r["ok"] is True

    def test_tempo_volume_decision_false_is_not_ok(self):
        r = self.ll.tempo_volume_decision(False)
        assert r["ok"] is False


# ══════════════════════════════════════════════════════════════════════════════
# 4. TRIMP ENGINE  (was standalone-only; now has full pytest coverage)
# ══════════════════════════════════════════════════════════════════════════════

class TestTRIMPEnginePytest:
    """
    Dedicated pytest class for TRIMPEngine.

    Extends the logic test with parametrized zone boundary checks and the
    weekly_trimp_analysis path not previously covered.
    """

    @pytest.fixture(autouse=True)
    def _t(self):
        from titan.science.trimp_engine import TRIMPEngine
        self.T = TRIMPEngine

    # ── Edwards TRIMP ────────────────────────────────────────────────────────

    def test_zero_max_hr_returns_none(self):
        trimp, zone = self.T.calculate_edwards_trimp(60, 150, 0)
        assert trimp is None and zone == 0

    def test_invalid_low_max_hr_returns_none(self):
        trimp, zone = self.T.calculate_edwards_trimp(60, 150, 50)
        assert trimp is None and zone == 0

    def test_zone4_at_84pct_hrmax(self):
        _, zone = self.T.calculate_edwards_trimp(60, 160, 190)
        assert zone == 4  # 160/190 ≈ 84.2% → zone 4

    def test_edwards_trimp_value_is_duration_times_multiplier(self):
        trimp, zone = self.T.calculate_edwards_trimp(60, 160, 190)
        assert trimp == 60 * zone

    @pytest.mark.parametrize("avg_hr,max_hr,expected_zone", [
        (55, 100, 1),   # 55% → zone 1 (< 60%)
        (65, 100, 2),   # 65% → zone 2 (60-70%)
        (75, 100, 3),   # 75% → zone 3 (70-80%)
        (85, 100, 4),   # 85% → zone 4 (80-90%)
        (95, 100, 5),   # 95% → zone 5 (≥ 90%)
    ])
    def test_edwards_zone_boundaries(self, avg_hr, max_hr, expected_zone):
        _, zone = self.T.calculate_edwards_trimp(60, avg_hr, max_hr)
        assert zone == expected_zone

    # ── Banister TRIMP ───────────────────────────────────────────────────────

    def test_banister_positive_for_valid_inputs(self):
        bt = self.T.calculate_banister_trimp(60, 160, 45, 190, "male")
        assert bt is not None and bt > 0

    def test_banister_returns_none_for_invalid_max_hr(self):
        assert self.T.calculate_banister_trimp(60, 160, 45, 40, "male") is None

    def test_banister_female_differs_from_male(self):
        male   = self.T.calculate_banister_trimp(60, 160, 45, 190, "male")
        female = self.T.calculate_banister_trimp(60, 160, 45, 190, "female")
        assert male != female

    # ── Zone-time TRIMP ──────────────────────────────────────────────────────

    def test_zone_time_trimp_basic(self):
        # 10min z1(×1) + 10min z2(×2) + 10min z3(×3) = 60
        assert self.T.calculate_zone_time_trimp([10, 10, 10, 0, 0]) == 60.0

    def test_zone_time_trimp_mismatched_lengths_zero(self):
        assert self.T.calculate_zone_time_trimp([10, 20]) == 0.0

    def test_zone_time_trimp_all_zeros(self):
        assert self.T.calculate_zone_time_trimp([0, 0, 0, 0, 0]) == 0.0

    # ── Weekly analysis ──────────────────────────────────────────────────────

    def test_weekly_analysis_zero_baseline_returns_unknown(self):
        _, risk = self.T.weekly_trimp_analysis(500, 0)
        assert risk == "UNKNOWN"

    def test_weekly_analysis_returns_string_tuple(self):
        msg, risk = self.T.weekly_trimp_analysis(500, 400)
        assert isinstance(msg, str) and isinstance(risk, str)

    @pytest.mark.parametrize("weekly,baseline,expected_risk", [
        (700, 400, "CRITICAL"),   # +75% → dangerous spike (> 50%)
        (540, 400, "HIGH_RISK"),  # +35% → spike (> 30%)
        (470, 400, "ELEVATED"),   # +17.5% → elevated (> 15%, strictly)
        (420, 400, "SAFE"),       # +5%  → optimal (-10% to +15%)
        (340, 400, "RECOVERY"),   # -15% → deload (-25% to -10%)
        (200, 400, "LOW"),        # -50% → severe deload (< -25%)
    ])
    def test_weekly_risk_levels(self, weekly, baseline, expected_risk):
        _, risk = self.T.weekly_trimp_analysis(weekly, baseline)
        assert risk == expected_risk


# ══════════════════════════════════════════════════════════════════════════════
# 5. ACWR ENGINE  (new — no previous pytest coverage)
# ══════════════════════════════════════════════════════════════════════════════

class TestACWREngine:
    """
    Dedicated pytest class for ACWREngine.

    This class was entirely missing from pytest; ACWR was only implicitly
    exercised via the standalone test_titan_logic.test_planner().
    """

    @pytest.fixture(autouse=True)
    def _a(self):
        from titan.science.acwr_engine import ACWREngine
        self.A = ACWREngine

    def test_zero_chronic_returns_none(self):
        val, status, _ = self.A.calculate_acwr(80, 0)
        assert val is None
        assert status == "INSUFFICIENT DATA"

    def test_sweet_spot_acwr(self):
        # acwr = acute / (chronic_avg * 7)
        # target 1.1 → acute = 1.1 * 10 * 7 = 77
        val, status, _ = self.A.calculate_acwr(77, 10)
        assert "SWEET SPOT" in status
        assert val == pytest.approx(1.1, abs=0.01)

    def test_high_injury_risk(self):
        # acwr > 1.5 → acute = 2.0 * 10 * 7 = 140
        _, status, _ = self.A.calculate_acwr(140, 10)
        assert "HIGH INJURY RISK" in status

    def test_severe_detraining(self):
        # acwr < 0.5 → acute = 0.2 * 10 * 7 = 14
        _, status, _ = self.A.calculate_acwr(14, 10)
        assert "DETRAINING" in status

    def test_maintenance_zone(self):
        # acwr = 0.9 → acute = 0.9 * 10 * 7 = 63
        _, status, _ = self.A.calculate_acwr(63, 10)
        assert "MAINTENANCE" in status

    def test_returns_rounded_acwr(self):
        val, _, _ = self.A.calculate_acwr(77, 10)
        assert val == round(val, 2)

    def test_weekly_load_recommendation(self):
        # chronic=10, target=1.2 → 10 * 7 * 1.2 = 84
        assert self.A.weekly_load_recommendation(10.0, target=1.2) == pytest.approx(84.0)

    @pytest.mark.parametrize("acwr,expected_score", [
        (0.5, 1),   # < 0.8 → Very Low
        (0.9, 2),   # ≤ 1.0 → Low
        (1.1, 3),   # ≤ 1.15 → Low-Moderate
        (1.2, 4),   # ≤ 1.3 → Moderate
        (1.4, 6),   # ≤ 1.5 → Moderate-High
        (1.6, 8),   # ≤ 1.7 → High
        (2.0, 10),  # > 1.7 → Extreme
    ])
    def test_injury_risk_score_levels(self, acwr, expected_score):
        score, _ = self.A.injury_risk_score(acwr)
        assert score == expected_score

    def test_injury_risk_score_returns_string_label(self):
        _, label = self.A.injury_risk_score(1.2)
        assert isinstance(label, str) and len(label) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 6. NUTRITION OPTIMIZER — edge cases  (new)
# ══════════════════════════════════════════════════════════════════════════════

class TestNutritionOptimizerPytest:
    """
    Extends nutrition coverage: extreme body weights, zero-duration sessions,
    fat floor enforcement, and the insufficient-data weight trend path.
    """

    @pytest.fixture
    def nut(self):
        from titan.features.nutrition_optimizer import NutritionOptimizer
        from titan.science.glycogen_model import GlycogenModel

        return NutritionOptimizer(GlycogenModel())

    def _plan(self, nut, weight, session):
        return nut.calculate_daily_nutrition(weight, session)

    # ── basic logic ──────────────────────────────────────────────────────────

    def test_long_run_carbs_above_300(self, nut):
        plan = self._plan(nut, 75.0, {
            "session_type": "LONG_RUN", "duration_min": 120,
            "distance_km": 20, "dew_point": 10,
        })
        assert plan["carbs_g"] > 300

    def test_hydration_higher_for_intense_sessions(self, nut):
        long_run = self._plan(nut, 75.0, {"session_type": "LONG_RUN", "duration_min": 120})
        easy     = self._plan(nut, 75.0, {"session_type": "EASY", "duration_min": 60})
        assert long_run["hydration_ml"] > easy["hydration_ml"]

    def test_weight_trend_works_after_entries(self, nut):
        for i in range(10):
            nut.add_weight_entry(f"2026-02-{i + 1:02d}", 75.0 - i * 0.05)
        assert "status" in nut.analyze_weight_trend()

    # ── edge cases ───────────────────────────────────────────────────────────

    def test_very_low_body_weight_stays_positive(self, nut):
        plan = self._plan(nut, 40.0, {"session_type": "EASY", "duration_min": 45})
        assert plan["carbs_g"] > 0
        assert plan["protein_g"] > 0

    def test_very_high_body_weight(self, nut):
        plan = self._plan(nut, 120.0, {"session_type": "TEMPO", "duration_min": 60})
        assert plan["carbs_g"] > 0
        assert plan["protein_g"] > 0

    def test_fat_floor_enforced(self, nut):
        """Minimum 40 g fat even on high-carb RACE day."""
        plan = self._plan(nut, 70.0, {"session_type": "RACE", "duration_min": 180})
        assert plan["fat_g"] >= 40

    def test_rest_day_lower_carbs_than_intervals(self, nut):
        rest      = self._plan(nut, 75.0, {"session_type": "REST",      "duration_min": 0})
        intervals = self._plan(nut, 75.0, {"session_type": "INTERVALS", "duration_min": 60})
        assert rest["carbs_g"] < intervals["carbs_g"]

    def test_race_day_highest_calories(self, nut):
        """RACE uses 2.0 multiplier — highest TDEE of all session types."""
        race = self._plan(nut, 75.0, {"session_type": "RACE", "duration_min": 180})
        rest = self._plan(nut, 75.0, {"session_type": "REST", "duration_min": 0})
        assert race["total_calories"] > rest["total_calories"]

    def test_insufficient_data_trend(self, nut):
        result = nut.analyze_weight_trend()
        assert result["status"] == "INSUFFICIENT_DATA"

    def test_result_has_required_keys(self, nut):
        plan = self._plan(nut, 75.0, {"session_type": "EASY", "duration_min": 45})
        for k in ("total_calories", "carbs_g", "protein_g", "fat_g", "hydration_ml"):
            assert k in plan, f"Missing key: {k}"

    def test_zero_duration_rest_day_no_crash(self, nut):
        plan = self._plan(nut, 75.0, {"session_type": "REST", "duration_min": 0})
        assert plan["carbs_g"] >= 0

    def test_weight_history_capped_at_90(self, nut):
        for i in range(100):
            nut.add_weight_entry(f"2025-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}", 75.0)
        assert len(nut.weight_history) <= 90


# ══════════════════════════════════════════════════════════════════════════════
# 7. WEEKLY PLANNER  (pytest migration)
# ══════════════════════════════════════════════════════════════════════════════

class TestWeeklyPlannerPytest:
    """Pytest port of test_titan_logic.test_planner()."""

    @pytest.fixture
    def planner(self):
        from titan.features.weekly_planner import WeeklyPlanGenerator
        from titan.science.acwr_engine import ACWREngine
        from titan.science.hrv_engine import HRVGuidedEngine
        from titan.science.tsb_engine import TSBEngine

        return WeeklyPlanGenerator(HRVGuidedEngine(), TSBEngine(), ACWREngine())

    def test_no_plan_fallback_type_easy(self, planner):
        assert planner.get_today_session()["session_type"] == "EASY"

    def test_no_plan_fallback_has_duration_min(self, planner):
        assert "duration_min" in planner.get_today_session()

    def test_generate_plan_seven_daily_sessions(self, planner):
        plan = planner.generate_weekly_plan({"threshold_hr": 170}, phase="BUILD")
        assert len(plan["daily_sessions"]) == 7

    def test_plan_has_quality_sessions(self, planner):
        plan = planner.generate_weekly_plan({"threshold_hr": 170}, phase="BUILD")
        assert plan["quality_count"] > 0

    def test_session_after_plan_has_duration_min(self, planner):
        planner.generate_weekly_plan({"threshold_hr": 170}, phase="BUILD")
        assert "duration_min" in planner.get_today_session()

    def test_non_rest_session_has_positive_duration(self, planner):
        planner.generate_weekly_plan({"threshold_hr": 170}, phase="BUILD")
        s = planner.get_today_session()
        if s["session_type"] != "REST":
            assert s["duration_min"] > 0


# ══════════════════════════════════════════════════════════════════════════════
# 8. DATABASE — thread safety  (pytest migration)
# ══════════════════════════════════════════════════════════════════════════════

class TestDatabaseThreadSafetyPytest:
    """Pytest port of test_titan_logic.test_database()."""

    def test_concurrent_reads_and_writes(self, tmp_path):
        import threading

        from titan.core.database import DatabaseManager

        db = DatabaseManager(str(tmp_path / "thread_test.db"))
        errors = []

        def writer(n):
            try:
                db.save_session(
                    date=f"2026-01-{n:02d}",
                    session_type="EASY",
                    distance_km=10.0,
                    duration_sec=3600,
                    avg_hr=140,
                    rpe=5,
                )
            except Exception as e:
                errors.append(str(e))

        def reader():
            try:
                db.get_training_load_history(42)
            except Exception as e:
                errors.append(str(e))

        threads = ([threading.Thread(target=writer, args=(i,)) for i in range(1, 11)]
                   + [threading.Thread(target=reader) for _ in range(5)])
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        db.close()

        assert errors == [], f"Threading errors: {errors[:2]}"
