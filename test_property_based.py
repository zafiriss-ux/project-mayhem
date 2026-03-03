#!/usr/bin/env python3
"""
Property-based tests using Hypothesis.

Targets modules with deterministic, mathematical contracts that are best
validated with randomised inputs rather than hand-picked examples:

  MathCore          — pace converters, format_pace, weight_function_Wf
  WeatherAPI        — dew_point always ≤ air_temp, finite output
  ACWREngine        — output always within documented risk bands
  GlycogenDebt      — debt always clamped 0-10 after update
  CriticalSpeed     — thermal CS always ≤ raw CS, ≥ 85% floor

Run with:
    pytest test_property_based.py -v
    pytest test_property_based.py --hypothesis-seed=0   # deterministic CI run
"""

import math
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("hypothesis", reason="Install test dependencies from requirements.txt")
from hypothesis import assume, given, settings
from hypothesis import strategies as st

os.environ.setdefault("GARMIN_EMAIL",        "test@example.com")
os.environ.setdefault("GARMIN_PASSWORD",     "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN",  "")
os.environ.setdefault("TELEGRAM_CHAT_ID",    "12345")
os.environ.setdefault("WEATHER_API_KEY",     "test")
os.environ.setdefault("WEATHER_LOCATION",    "Athens,GR")

sys.path.insert(0, str(Path(__file__).parent))


# ════════════════════════════════════════════════════════════════════════════
# 1. MathCore — pace converters
# ════════════════════════════════════════════════════════════════════════════

class TestMathCoreProperties:

    @given(pace=st.floats(min_value=120.0, max_value=900.0))
    def test_pace_to_ms_roundtrip(self, pace):
        """pace (sec/km) → m/s → pace must round-trip within 1 s/km."""
        from titan.utils.math_core import MathCore
        speed = MathCore.pace_to_ms(pace)
        assert speed > 0
        back = MathCore.ms_to_pace(speed)
        assert abs(back - pace) < 1.0

    @given(pace=st.floats(min_value=120.0, max_value=900.0))
    def test_faster_pace_gives_higher_speed(self, pace):
        """Lower pace (fewer sec/km) = faster = higher m/s."""
        from titan.utils.math_core import MathCore
        assume(pace < 890)  # ensure pace+10 is still in valid range
        speed_faster = MathCore.pace_to_ms(pace)
        speed_slower = MathCore.pace_to_ms(pace + 10)
        assert speed_faster > speed_slower

    @given(pace=st.floats(min_value=1.0, max_value=900.0))
    def test_pace_to_ms_always_positive(self, pace):
        from titan.utils.math_core import MathCore
        assert MathCore.pace_to_ms(pace) >= 0

    @given(speed=st.floats(min_value=0.5, max_value=10.0))
    def test_ms_to_pace_always_positive(self, speed):
        from titan.utils.math_core import MathCore
        assert MathCore.ms_to_pace(speed) >= 0

    @given(
        minutes=st.integers(min_value=0, max_value=59),
        seconds=st.integers(min_value=0, max_value=59),
    )
    def test_format_pace_output_is_M_SS(self, minutes, seconds):
        """format_pace(sec/km) must return a string in M:SS format."""
        from titan.utils.math_core import MathCore
        pace_sec = minutes * 60 + seconds
        assume(pace_sec > 0)
        result = MathCore.format_pace(float(pace_sec))
        parts = result.split(":")
        assert len(parts) == 2
        assert parts[1].isdigit() and len(parts[1]) == 2


# ════════════════════════════════════════════════════════════════════════════
# 2. WeatherAPI — dew point properties
# ════════════════════════════════════════════════════════════════════════════

class TestWeatherDewPointProperties:

    @given(
        temp_c=st.floats(min_value=-20.0, max_value=50.0),
        humidity=st.floats(min_value=1.0, max_value=100.0),
    )
    def test_dew_point_never_exceeds_air_temp(self, temp_c, humidity):
        """Dew point is always ≤ air temperature (physical law)."""
        from titan.integrations.weather_api import WeatherAPI
        dp = WeatherAPI.calculate_dew_point(temp_c, humidity)
        assert dp <= temp_c + 0.1  # small tolerance for float rounding

    @given(
        temp_c=st.floats(min_value=-20.0, max_value=50.0),
        humidity=st.floats(min_value=1.0, max_value=100.0),
    )
    def test_dew_point_is_finite(self, temp_c, humidity):
        """calculate_dew_point must never return NaN or inf."""
        from titan.integrations.weather_api import WeatherAPI
        dp = WeatherAPI.calculate_dew_point(temp_c, humidity)
        assert math.isfinite(dp)

    @given(
        temp_c=st.floats(min_value=0.0, max_value=40.0),
        rh_low=st.floats(min_value=10.0, max_value=50.0),
        rh_high=st.floats(min_value=60.0, max_value=100.0),
    )
    def test_higher_humidity_gives_higher_dew_point(self, temp_c, rh_low, rh_high):
        """At the same temperature, higher RH → higher dew point."""
        from titan.integrations.weather_api import WeatherAPI
        dp_low  = WeatherAPI.calculate_dew_point(temp_c, rh_low)
        dp_high = WeatherAPI.calculate_dew_point(temp_c, rh_high)
        assert dp_high >= dp_low


# ════════════════════════════════════════════════════════════════════════════
# 3. ACWREngine — output always within documented bands
# ════════════════════════════════════════════════════════════════════════════

class TestACWREngineProperties:

    @given(
        acute=st.floats(min_value=0.1, max_value=500.0),
        chronic=st.floats(min_value=1.0, max_value=200.0),
    )
    def test_acwr_value_is_non_negative(self, acute, chronic):
        from titan.science.acwr_engine import ACWREngine
        val, _, _ = ACWREngine.calculate_acwr(acute, chronic)
        assert val is not None
        assert val >= 0

    @given(
        acute=st.floats(min_value=0.1, max_value=500.0),
        chronic=st.floats(min_value=1.0, max_value=200.0),
    )
    def test_acwr_status_is_non_empty_string(self, acute, chronic):
        from titan.science.acwr_engine import ACWREngine
        _, status, _ = ACWREngine.calculate_acwr(acute, chronic)
        assert isinstance(status, str) and len(status) > 0

    @given(
        acwr=st.floats(min_value=0.0, max_value=5.0),
    )
    def test_injury_risk_score_is_1_to_10(self, acwr):
        from titan.science.acwr_engine import ACWREngine
        score, label = ACWREngine.injury_risk_score(acwr)
        assert 1 <= score <= 10
        assert isinstance(label, str)


# ════════════════════════════════════════════════════════════════════════════
# 4. GlycogenDebtAccumulator — debt always clamped [0, 10]
# ════════════════════════════════════════════════════════════════════════════

class TestGlycogenDebtProperties:

    @given(
        trimp=st.floats(min_value=0.0, max_value=500.0),
        time_lt2=st.floats(min_value=0.0, max_value=120.0),
        dprime=st.floats(min_value=0.0, max_value=1.0),
        carb_g=st.floats(min_value=0.0, max_value=150.0),
        weight=st.floats(min_value=40.0, max_value=130.0),
    )
    @settings(max_examples=50)
    def test_debt_always_clamped_0_to_10(self, trimp, time_lt2, dprime, carb_g, weight):
        from titan.science.glycogen_model import GlycogenDebtAccumulator
        acc = GlycogenDebtAccumulator()
        acc.update("2026-01-01", trimp=trimp, time_above_lt2_min=time_lt2,
                   dprime_fraction=dprime, intra_carb_g=carb_g, weight_kg=weight)
        assert 0.0 <= acc.daily_debt <= 10.0

    @given(
        trimp=st.floats(min_value=50.0, max_value=300.0),
        carb_low=st.floats(min_value=0.0, max_value=30.0),
        carb_high=st.floats(min_value=80.0, max_value=150.0),
    )
    def test_more_carbs_lower_debt(self, trimp, carb_low, carb_high):
        from titan.science.glycogen_model import GlycogenDebtAccumulator
        acc_low  = GlycogenDebtAccumulator()
        acc_high = GlycogenDebtAccumulator()
        acc_low.update("2026-01-01",  trimp=trimp, time_above_lt2_min=20,
                       dprime_fraction=0.0, intra_carb_g=carb_low,  weight_kg=70)
        acc_high.update("2026-01-01", trimp=trimp, time_above_lt2_min=20,
                        dprime_fraction=0.0, intra_carb_g=carb_high, weight_kg=70)
        assert acc_high.daily_debt <= acc_low.daily_debt


# ════════════════════════════════════════════════════════════════════════════
# 5. CriticalSpeedTracker — thermal always ≤ raw CS, ≥ 85% floor
# ════════════════════════════════════════════════════════════════════════════

class TestCriticalSpeedProperties:

    @given(
        cs_raw=st.floats(min_value=1.0, max_value=8.0),
        temp_c=st.floats(min_value=0.0, max_value=50.0),
    )
    def test_thermal_never_exceeds_raw_cs(self, cs_raw, temp_c):
        from titan.science.critical_speed import CriticalSpeedTracker
        tracker = CriticalSpeedTracker()
        tracker.update("2026-01-01", cs_raw=cs_raw, d_prime=200.0)
        cs_thermal = tracker.apply_thermal(temp_c)
        assert cs_thermal <= tracker.cs_smoothed + 0.001  # apply_thermal rounds to 3dp

    @given(
        cs_raw=st.floats(min_value=2.0, max_value=6.0),
        temp_c=st.floats(min_value=20.1, max_value=50.0),
    )
    def test_thermal_floor_at_85_pct(self, cs_raw, temp_c):
        """Even at extreme heat, thermal CS ≥ 85% of smoothed CS."""
        from titan.science.critical_speed import CriticalSpeedTracker
        tracker = CriticalSpeedTracker()
        tracker.update("2026-01-01", cs_raw=cs_raw, d_prime=200.0)
        cs_thermal = tracker.apply_thermal(temp_c)
        floor = tracker.cs_smoothed * 0.85
        assert cs_thermal >= floor - 0.001  # apply_thermal rounds to 3dp

    @given(
        cs_raw=st.floats(min_value=1.0, max_value=8.0),
    )
    def test_thermal_no_degradation_below_20c(self, cs_raw):
        from titan.science.critical_speed import CriticalSpeedTracker
        tracker = CriticalSpeedTracker()
        tracker.update("2026-01-01", cs_raw=cs_raw, d_prime=200.0)
        assert tracker.apply_thermal(15.0) == pytest.approx(tracker.cs_smoothed, abs=0.001)

    @given(
        grade_pct=st.floats(min_value=-20.0, max_value=20.0),
        pace_sec_per_km=st.floats(min_value=150.0, max_value=600.0),
    )
    def test_gap_flat_unchanged(self, grade_pct, pace_sec_per_km):
        from titan.science.critical_speed import CriticalSpeedTracker
        assume(abs(grade_pct) < 0.01)  # only test truly flat
        corrected = CriticalSpeedTracker.gap_correct_pace(pace_sec_per_km, grade_pct)
        assert corrected == pytest.approx(pace_sec_per_km, abs=0.1)

    @given(
        grade_pct=st.floats(min_value=1.0, max_value=20.0),
        pace_sec_per_km=st.floats(min_value=150.0, max_value=600.0),
    )
    def test_gap_uphill_reduces_effective_pace(self, grade_pct, pace_sec_per_km):
        """Uphill grade → GAP corrected pace < raw pace (faster equivalent)."""
        from titan.science.critical_speed import CriticalSpeedTracker
        corrected = CriticalSpeedTracker.gap_correct_pace(pace_sec_per_km, grade_pct)
        assert corrected <= pace_sec_per_km


# ════════════════════════════════════════════════════════════════════════════
# 6. ReadinessEngine — score always 0-100, status always a string
# ════════════════════════════════════════════════════════════════════════════

class TestReadinessEngineProperties:

    @given(
        today_hrv   =st.floats(min_value=0.0, max_value=120.0),
        baseline_hrv=st.floats(min_value=0.1, max_value=120.0),
        today_rhr   =st.integers(min_value=30, max_value=120),
        baseline_rhr=st.integers(min_value=30, max_value=120),
        sleep_score =st.integers(min_value=0, max_value=100),
        soreness    =st.integers(min_value=0, max_value=10),
    )
    def test_score_always_0_to_100(self, today_hrv, baseline_hrv,
                                    today_rhr, baseline_rhr,
                                    sleep_score, soreness):
        from titan.science.readiness_engine import ReadinessEngine
        r = ReadinessEngine.analyze_readiness(
            today_hrv=today_hrv, baseline_hrv=baseline_hrv,
            today_rhr=today_rhr, baseline_rhr=baseline_rhr,
            sleep_score=sleep_score, soreness=soreness,
        )
        assert 0 <= r["score"] <= 100

    @given(
        today_hrv   =st.floats(min_value=0.0, max_value=120.0),
        baseline_hrv=st.floats(min_value=0.1, max_value=120.0),
        today_rhr   =st.integers(min_value=30, max_value=120),
        baseline_rhr=st.integers(min_value=30, max_value=120),
        sleep_score =st.integers(min_value=0, max_value=100),
        soreness    =st.integers(min_value=0, max_value=10),
    )
    def test_status_always_non_empty_string(self, today_hrv, baseline_hrv,
                                             today_rhr, baseline_rhr,
                                             sleep_score, soreness):
        from titan.science.readiness_engine import ReadinessEngine
        r = ReadinessEngine.analyze_readiness(
            today_hrv=today_hrv, baseline_hrv=baseline_hrv,
            today_rhr=today_rhr, baseline_rhr=baseline_rhr,
            sleep_score=sleep_score, soreness=soreness,
        )
        assert isinstance(r["status"], str) and len(r["status"]) > 0
