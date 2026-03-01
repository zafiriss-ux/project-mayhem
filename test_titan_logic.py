#!/usr/bin/env python3
"""
TITAN Logic Integrity Test
Runs without real API keys to verify internal math and logic flow.

Usage:
    python test_titan_logic.py
"""

import sys
import os

# Fake credentials so integration classes don't crash on import
os.environ.setdefault("GARMIN_EMAIL",     "test@example.com")
os.environ.setdefault("GARMIN_PASSWORD",  "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("WEATHER_API_KEY",  "test")
os.environ.setdefault("WEATHER_LOCATION", "Athens,GR")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []

def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    msg = f"  {status}  {name}" + (f"  [{detail}]" if detail else "")
    print(msg)
    results.append((name, condition))
    return condition


# ════════════════════════════════════════════════════════════════════════════
# 1. HRV ENGINE
# ════════════════════════════════════════════════════════════════════════════
def test_hrv():
    print("\n🧪 HRV Engine")
    from titan.science.hrv_engine import HRVGuidedEngine
    hrv = HRVGuidedEngine()

    # Empty state
    s = hrv.get_hrv_summary()
    check("get_hrv_summary() on empty log returns 0s",
          s['latest_hrv'] == 0.0 and s['baseline'] == 0.0)

    # Feed 8 days of data
    for i, val in enumerate([55, 58, 60, 57, 62, 61, 63, 67]):
        hrv.add_hrv_measurement(f"2026-02-{10+i:02d}", val)

    s = hrv.get_hrv_summary()
    check("latest_hrv is correct after feeding data", s['latest_hrv'] == 67.0)
    check("baseline > 0 with 8 data points",          s['baseline'] > 0)
    check("data_points == 8",                          s['data_points'] == 8)

    # High HRV → proceed with planned session
    rec, msg, _ = hrv.get_training_recommendation(68, "INTERVALS")
    check("High HRV → proceed with INTERVALS", rec == "INTERVALS")

    # Very low HRV → downgrade
    rec, msg, _ = hrv.get_training_recommendation(30, "INTERVALS")
    check("Very low HRV → REST or EASY", rec in ("REST", "EASY"))


# ════════════════════════════════════════════════════════════════════════════
# 2. READINESS ENGINE
# ════════════════════════════════════════════════════════════════════════════
def test_readiness():
    print("\n🧪 Readiness Engine (sleep_score scale 0-100)")
    from titan.science.readiness_engine import ReadinessEngine

    # Good night (sleep_score 85)
    r = ReadinessEngine.analyze_readiness(
        today_hrv=62, baseline_hrv=60,
        today_rhr=47, baseline_rhr=48,
        sleep_score=85, soreness=2,
    )
    check("Good night: score > 80", r['score'] > 80, f"score={r['score']}")

    # Bad night (sleep_score 40)
    r_bad = ReadinessEngine.analyze_readiness(
        today_hrv=50, baseline_hrv=62,
        today_rhr=55, baseline_rhr=48,
        sleep_score=40, soreness=4,
    )
    check("Bad night: score < good night score",
          r_bad['score'] < r['score'],
          f"bad={r_bad['score']} good={r['score']}")
    check("Bad night: status is not EXCELLENT",
          r_bad['status'] not in ("✅ EXCELLENT",),
          r_bad['status'])

    # Score always 0-100
    check("Score clamped 0-100", 0 <= r['score'] <= 100)


# ════════════════════════════════════════════════════════════════════════════
# 3. LACTATE LOGIC
# ════════════════════════════════════════════════════════════════════════════
def test_lactate():
    print("\n🧪 Lactate Logic (dict returns)")
    from titan.science.lactate_logic import LactateLogic

    r1 = LactateLogic.estimate_lt1(75.0, 2.5)
    check("LT1 detected correctly (hr=75%, drift=2.5%)", r1['is_lt1'] is True)
    check("LT1 result is dict with 'is_lt1' key", 'is_lt1' in r1)

    r2 = LactateLogic.estimate_lt1(82.0, 4.0)
    check("LT1 not detected (hr=82%, drift=4%)", r2['is_lt1'] is False)

    r3 = LactateLogic.estimate_lt2(hr_stable=True, rpe=6.5)
    check("LT2 detected (stable HR + RPE 6.5)", r3['is_lt2'] is True)

    r4 = LactateLogic.tempo_volume_decision(True)
    check("tempo_volume_decision returns dict with 'ok' key", 'ok' in r4)
    check("is_lt2=True → ok=True", r4['ok'] is True)


# ════════════════════════════════════════════════════════════════════════════
# 4. TRIMP ENGINE
# ════════════════════════════════════════════════════════════════════════════
def test_trimp():
    print("\n🧪 TRIMP Engine")
    from titan.science.trimp_engine import TRIMPEngine

    # Invalid max_hr
    trimp, zone = TRIMPEngine.calculate_edwards_trimp(60, 150, 0)
    check("max_hr=0 → returns (None, 0)", trimp is None and zone == 0)

    trimp, zone = TRIMPEngine.calculate_edwards_trimp(60, 150, 50)
    check("max_hr=50 (invalid) → returns (None, 0)", trimp is None and zone == 0)

    # Valid
    trimp, zone = TRIMPEngine.calculate_edwards_trimp(60, 160, 190)
    # (160 / 190) * 100 ≈ 84.2% → zone 4 (×4)
    check("60min @ 84% HRmax → zone 4", zone == 4)
    check("TRIMP = 60 × 4 = 240", trimp == 240)

    # Banister
    bt = TRIMPEngine.calculate_banister_trimp(60, 160, 45, 190, 'male')
    check("Banister TRIMP > 0 for valid inputs", bt is not None and bt > 0)

    bt_bad = TRIMPEngine.calculate_banister_trimp(60, 160, 45, 40, 'male')
    check("Banister TRIMP returns None for invalid max_hr", bt_bad is None)


# ════════════════════════════════════════════════════════════════════════════
# 5. MATH CORE — unit converters
# ════════════════════════════════════════════════════════════════════════════
def test_math_core():
    print("\n🧪 MathCore — Unit Converters")
    from titan.utils.math_core import MathCore

    ms = MathCore.pace_to_ms(240)   # 4:00/km
    check("pace_to_ms(240) ≈ 4.167 m/s", abs(ms - 4.1667) < 0.001, f"{ms}")

    pace = MathCore.ms_to_pace(4.1667)
    check("ms_to_pace(4.1667) ≈ 240 sec/km", abs(pace - 240) < 1, f"{pace}")

    check("pace_to_ms(0) == 0.0", MathCore.pace_to_ms(0) == 0.0)
    check("ms_to_pace(0) == 0.0", MathCore.ms_to_pace(0) == 0.0)

    fmt = MathCore.format_pace(240)
    check("format_pace(240) == '4:00'", fmt == "4:00", fmt)

    # Profile-aware weight function
    status = MathCore.weight_function_from_profile(74.0, 0.5, 100, target_weight=75.0)
    check("74.0 kg < 74.5 (target 75 - 0.5) → AGGRESSIVE_CORRECTION", status == "AGGRESSIVE_CORRECTION", status)

    status2 = MathCore.weight_function_from_profile(76.0, 0.5, 100, target_weight=75.0)
    check("76.0 kg (stable range) → STABLE", status2 == "STABLE", status2)


# ════════════════════════════════════════════════════════════════════════════
# 6. NUTRITION OPTIMIZER — hydration with dew point + intensity
# ════════════════════════════════════════════════════════════════════════════
def test_nutrition():
    print("\n🧪 Nutrition Optimizer")
    from titan.science.glycogen_model import GlycogenModel
    from titan.features.nutrition_optimizer import NutritionOptimizer

    nut = NutritionOptimizer(GlycogenModel())

    # Long run
    plan = nut.calculate_daily_nutrition(
        75.0,
        {"session_type": "LONG_RUN", "duration_min": 120, "distance_km": 20, "dew_point": 10}
    )
    check("Long run: carbs > 300g", plan['carbs_g'] > 300, f"carbs={plan['carbs_g']}")
    check("Long run 120min @ dp=10: hydration ≥ 1000ml",
          plan['hydration_ml'] >= 1000, f"{plan['hydration_ml']}ml")

    # Oppressive heat intervals (dp=22) → more fluid
    hot_plan = nut.calculate_daily_nutrition(
        75.0,
        {"session_type": "INTERVALS", "duration_min": 60, "distance_km": 12, "dew_point": 22}
    )
    mild_plan = nut.calculate_daily_nutrition(
        75.0,
        {"session_type": "INTERVALS", "duration_min": 60, "distance_km": 12, "dew_point": 10}
    )
    check("Oppressive heat needs more fluid than mild",
          hot_plan['hydration_ml'] > mild_plan['hydration_ml'],
          f"hot={hot_plan['hydration_ml']} mild={mild_plan['hydration_ml']}")

    # Weight trend
    for i in range(10):
        nut.add_weight_entry(f"2026-02-{i+1:02d}", 75.0 - i * 0.05)
    trend = nut.analyze_weight_trend()
    check("Weight trend analysis works", 'status' in trend)


# ════════════════════════════════════════════════════════════════════════════
# 7. WEEKLY PLANNER — get_today_session always returns duration_min
# ════════════════════════════════════════════════════════════════════════════
def test_planner():
    print("\n🧪 Weekly Planner")
    from titan.science.hrv_engine import HRVGuidedEngine
    from titan.science.tsb_engine import TSBEngine
    from titan.science.acwr_engine import ACWREngine
    from titan.features.weekly_planner import WeeklyPlanGenerator

    planner = WeeklyPlanGenerator(HRVGuidedEngine(), TSBEngine(), ACWREngine())

    # No plan → safe EASY fallback with duration_min
    s = planner.get_today_session()
    check("No plan → fallback session_type=EASY", s['session_type'] == 'EASY')
    check("No plan → fallback has duration_min", 'duration_min' in s)

    # Generate plan → today's session has duration_min
    plan = planner.generate_weekly_plan({'threshold_hr': 170}, phase='BUILD')
    check("Plan has 7 daily sessions", len(plan['daily_sessions']) == 7)
    check("Plan has quality sessions > 0", plan['quality_count'] > 0)

    s2 = planner.get_today_session()
    check("After generate: session has duration_min", 'duration_min' in s2)
    check("After generate: duration_min > 0 for non-REST",
          s2['duration_min'] > 0 if s2['session_type'] != 'REST' else True)


# ════════════════════════════════════════════════════════════════════════════
# 8. DATABASE — thread safety
# ════════════════════════════════════════════════════════════════════════════
def test_database():
    print("\n🧪 Database Thread Safety")
    import threading
    from titan.core.database import DatabaseManager

    db = DatabaseManager("test_thread_check.db")
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

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(1, 11)]
    threads += [threading.Thread(target=reader) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check("No threading errors with concurrent reads/writes",
          len(errors) == 0, f"{errors[:2]}" if errors else "")

    # Cleanup test DB
    try:
        import pathlib
        base = pathlib.Path(__file__).parent
        (base / "test_thread_check.db").unlink(missing_ok=True)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  TITAN v51 — Logic Integrity Test Suite")
    print("=" * 60)

    test_hrv()
    test_readiness()
    test_lactate()
    test_trimp()
    test_math_core()
    test_nutrition()
    test_planner()
    test_database()

    total   = len(results)
    passed  = sum(1 for _, ok in results if ok)
    failed  = total - passed

    print("\n" + "=" * 60)
    if failed == 0:
        print(f"  🎉 ALL {total} TESTS PASSED")
    else:
        print(f"  ⚠️  {passed}/{total} PASSED  |  {failed} FAILED")
        print("\n  Failed tests:")
        for name, ok in results:
            if not ok:
                print(f"    ❌ {name}")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
