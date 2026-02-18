#!/usr/bin/env python3
"""
Pytest suite for TITAN core modules.

Run with:
    pytest test_core_modules.py -v
    pytest test_core_modules.py -q   # quiet / CI mode
"""

import warnings
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# ── path setup ──────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from titan.core import (
    UniversalAthleteProfile,
    DatabaseManager,
    AthleteDatabase,
    EquipmentManager,
    PeriodizationManager,
)
from titan.utils import (
    MathCore,
    SESSION_TYPES,
    ACWR_SAFE_MIN,
    ACWR_SAFE_MAX,
    DEFAULT_CONFIG,
)
from titan.integrations.weather_api import WeatherAPI


# ══════════════════════════════════════════════════════════════════════════════
# SHARED FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def athlete():
    """Standard male athlete used across multiple test classes."""
    a = UniversalAthleteProfile(name="Test Runner")
    a.set_demographics("M", 30, 180, 75.0)
    a.set_hr_data(45, 190)
    return a


@pytest.fixture
def db(tmp_path):
    """Isolated DatabaseManager backed by a tmp_path file; auto-closed."""
    d = DatabaseManager(db_name=str(tmp_path / "test_titan.db"))
    yield d
    d.close()


@pytest.fixture
def populated_db(db):
    """DB pre-loaded with a daily metric and four training sessions."""
    db.save_daily_metric(
        date="2026-02-13",
        weight=75.2,
        hrv=65,
        rhr=45,
        sleep_hours=7.5,
        sleep_quality=80,
    )
    sessions = [
        ("2026-02-10", "EASY",      8.0, 2400, 7),
        ("2026-02-11", "TEMPO",    10.0, 2400, 8),
        ("2026-02-12", "INTERVALS", 6.0, 2100, 9),
        ("2026-02-13", "EASY",      7.0, 2100, 6),
    ]
    for date, stype, dist, dur, rpe in sessions:
        db.save_session(
            date=date, session_type=stype,
            distance_km=dist, duration_sec=dur, rpe=rpe,
        )
    return db


@pytest.fixture
def athlete_db(tmp_path):
    """Isolated AthleteDatabase using a tmp_path directory."""
    adb = AthleteDatabase(db_path=str(tmp_path / "athletes"))
    return adb


@pytest.fixture
def api():
    """WeatherAPI instance (no network calls needed — uses built-in sim data)."""
    return WeatherAPI()


# ══════════════════════════════════════════════════════════════════════════════
# 1. ATHLETE PROFILE
# ══════════════════════════════════════════════════════════════════════════════

class TestAthleteProfile:

    def test_basic_attributes(self, athlete):
        assert athlete.name == "Test Runner"
        assert athlete.age == 30
        assert athlete.weight_kg == 75.0
        assert athlete.resting_hr == 45
        assert athlete.max_hr == 190

    def test_bmr_physiological_range(self, athlete):
        bmr = athlete.calculate_bmr()
        assert 1700 < bmr < 2100, f"BMR {bmr} outside expected range"

    def test_tdee_greater_than_bmr(self, athlete):
        assert athlete.calculate_tdee() > athlete.calculate_bmr()

    def test_serialization_roundtrip(self, athlete):
        data = athlete.to_dict()
        restored = UniversalAthleteProfile.from_dict(data)
        assert restored.name == athlete.name
        assert restored.age == athlete.age
        assert restored.weight_kg == athlete.weight_kg
        assert restored.resting_hr == athlete.resting_hr
        assert restored.max_hr == athlete.max_hr

    def test_threshold_hr_between_resting_and_max(self, athlete):
        assert athlete.resting_hr < athlete.threshold_hr < athlete.max_hr


# ══════════════════════════════════════════════════════════════════════════════
# 2. PERIODIZATION
# ══════════════════════════════════════════════════════════════════════════════

class TestPeriodization:

    @pytest.fixture
    def pm(self, athlete):
        manager = PeriodizationManager(athlete)
        manager.add_goal(21.1, "1:30:00", "2026-04-26")
        return manager

    @pytest.mark.parametrize("days_out,expected_phase", [
        (80,  "BASE"),
        (50,  "BUILD"),
        (20,  "PEAK"),
        (5,   "TAPER"),
        (-1,  "POST_RACE"),
    ])
    def test_phase_transitions(self, pm, days_out, expected_phase):
        race_date = datetime.now() + timedelta(days=days_out)
        assert pm.calculate_phase(race_date) == expected_phase

    def test_goal_fields(self, pm):
        goal = pm.goals[0] if pm.goals else {}
        assert goal.get("distance_km") == pytest.approx(21.1)
        assert "race_date" in goal


# ══════════════════════════════════════════════════════════════════════════════
# 3. EQUIPMENT
# ══════════════════════════════════════════════════════════════════════════════

class TestEquipment:

    @pytest.fixture
    def em(self):
        return EquipmentManager()

    def test_race_shoe_on_track_passes(self, em):
        ok, _ = em.check_gear("INTERVALS", "1", "TRACK")
        assert ok is True

    def test_recovery_shoe_blocks_intervals(self, em):
        ok, _ = em.check_gear("INTERVALS", "3", "CONCRETE")
        assert ok is False

    def test_check_gear_returns_string_message(self, em):
        _, msg = em.check_gear("EASY", "2", "ROAD")
        assert isinstance(msg, str) and len(msg) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. DATABASE — canonical API + deprecated alias
# ══════════════════════════════════════════════════════════════════════════════

class TestDatabase:

    def test_save_and_retrieve_daily_metric(self, populated_db):
        ctl, atl, tsb = populated_db.get_ctl_atl_tsb()
        # Values are floats or None — just ensure no exception and types are correct
        assert ctl is None or isinstance(ctl, (int, float))
        assert atl is None or isinstance(atl, (int, float))
        assert tsb is None or isinstance(tsb, (int, float))

    def test_temperature_c_canonical(self, db):
        """save_session accepts temperature_c without warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            db.save_session(
                date="2026-02-14", session_type="EASY",
                distance_km=5.0, duration_sec=1800,
                temperature_c=15.0,
            )
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) == 0

    def test_temperature_deprecated_alias_warns(self, db):
        """save_session(temperature=...) emits DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            db.save_session(
                date="2026-02-15", session_type="EASY",
                distance_km=5.0, duration_sec=1800,
                temperature=15.0,
            )
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) >= 1

    def test_shoe_lifecycle(self, db):
        shoe_id = db.add_shoe("Test Shoe", "DAILY", 800)
        assert shoe_id is not None
        available, msg = db.check_shoe_availability(shoe_id)
        assert isinstance(available, bool)
        assert isinstance(msg, str)

    def test_personal_best_roundtrip(self, db):
        db.save_personal_best(5.0, 1140, "2026-02-13", "Test 5K")
        pr = db.get_pr(5.0)
        assert pr is not None
        time_sec, _, _ = pr
        assert time_sec == 1140

    def test_thread_safety_concurrent_writes(self, db):
        """Multiple threads writing sessions must not raise or corrupt DB."""
        import threading, time

        errors = []

        def write_sessions(start_day):
            for i in range(3):
                try:
                    db.save_session(
                        date=f"2026-01-{start_day + i:02d}",
                        session_type="EASY",
                        distance_km=5.0 + i,
                        duration_sec=1800,
                    )
                except Exception as e:
                    errors.append(str(e))

        threads = [threading.Thread(target=write_sessions, args=(i * 5 + 1,))
                   for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Thread-safety errors: {errors}"


# ══════════════════════════════════════════════════════════════════════════════
# 5. ATHLETE DATABASE
# ══════════════════════════════════════════════════════════════════════════════

class TestAthleteDatabase:

    def test_create_and_list(self, athlete_db):
        # Athlete IDs are timestamp-based; create one and verify it appears.
        a1 = athlete_db.create_athlete("Runner One", "M", 30, 180, 75)
        all_athletes = athlete_db.list_all()
        assert len(all_athletes) >= 1
        assert any(a["name"] == "Runner One" for a in all_athletes)

    def test_switch_athlete(self, athlete_db):
        a1 = athlete_db.create_athlete("Switch Target", "M", 25, 175, 70)
        athlete_db.switch_athlete(a1.athlete_id)
        current = athlete_db.get_current()
        assert current.name == "Switch Target"


# ══════════════════════════════════════════════════════════════════════════════
# 6. MATH CORE
# ══════════════════════════════════════════════════════════════════════════════

class TestMathCore:

    @pytest.mark.parametrize("weight,night_drop,epoc,expected", [
        (74.0, 0.5, 300, "AGGRESSIVE_CORRECTION"),
        (74.8, 0.5, 300, "EMERGENCY_MODE"),
        (75.2, 1.3, 300, "NIGHT_DROP_ALERT"),
        (75.5, 0.5, 360, "EPOC_OVERRIDE"),
        (75.3, 0.5, 300, "SAFE_DROP_RULE"),
        (76.0, 0.5, 300, "STABLE"),
    ])
    def test_weight_function(self, weight, night_drop, epoc, expected):
        result = MathCore.weight_function_Wf(weight, night_drop, epoc)
        assert result == expected

    @pytest.mark.parametrize("hrv,sleep,pain,expected_status", [
        ("LOW",    70, 1, "CRITICAL"),   # HRV suppressed
        ("NORMAL", 55, 1, "CRITICAL"),   # poor sleep
        ("NORMAL", 70, 4, "CRITICAL"),   # high pain
        ("NORMAL", 70, 2, "UNSTABLE"),   # moderate pain
        ("NORMAL", 62, 1, "UNSTABLE"),   # suboptimal sleep
        ("NORMAL", 75, 1, "STABLE"),     # all good
    ])
    def test_system_status(self, hrv, sleep, pain, expected_status):
        result = MathCore.system_status_SSV(hrv, sleep, pain, 75.5, 300, 0.5)
        assert result == expected_status

    def test_pace_converters_roundtrip(self):
        """pace (sec/km) → m/s → pace (sec/km) should round-trip."""
        pace_sec_per_km = 300.0  # 5:00 /km = 300 sec/km
        speed_ms = MathCore.pace_to_ms(pace_sec_per_km)
        assert abs(speed_ms - (1000.0 / 300.0)) < 0.01
        pace_back = MathCore.ms_to_pace(speed_ms)
        assert abs(pace_back - pace_sec_per_km) < 0.5
        # format_pace takes sec/km and returns "M:SS"
        formatted = MathCore.format_pace(pace_sec_per_km)
        assert formatted == "5:00"


# ══════════════════════════════════════════════════════════════════════════════
# 7. CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

class TestConstants:

    def test_session_types_non_empty(self):
        assert len(SESSION_TYPES) >= 5

    def test_acwr_safe_range_ordered(self):
        assert ACWR_SAFE_MIN < ACWR_SAFE_MAX

    def test_hr_zones_defined(self):
        zones = DEFAULT_CONFIG.get("hr_zones", {})
        assert len(zones) >= 4
        for zone, bounds in zones.items():
            low, high = bounds
            assert low < high, f"Zone {zone}: low={low} >= high={high}"


# ══════════════════════════════════════════════════════════════════════════════
# 8. WEATHER — Magnus-Tetens dew point (the corrected formula)
# ══════════════════════════════════════════════════════════════════════════════

class TestWeatherDewPoint:
    """
    Validates the August-Roche-Magnus dew point formula against published
    literature values (Lawrence 2005, BAMS 86(2), 225-234).
    """

    @pytest.mark.parametrize("temp_c,humidity,expected_dp,tolerance", [
        (20.0, 50.0,  9.3, 0.5),   # classic text-book check
        (25.0, 80.0, 21.4, 0.5),   # warm humid
        (10.0, 90.0,  8.4, 0.5),   # cool damp
        (30.0, 30.0, 10.5, 0.5),   # hot dry
    ])
    def test_known_dew_point_values(self, api, temp_c, humidity, expected_dp, tolerance):
        dp = api.calculate_dew_point(temp_c, humidity)
        assert abs(dp - expected_dp) <= tolerance, (
            f"T={temp_c}°C RH={humidity}%: got Td={dp}, expected ≈{expected_dp}±{tolerance}"
        )

    def test_dew_point_not_exceed_air_temp(self, api):
        """Dew point must always be ≤ air temperature."""
        for temp in range(0, 40, 5):
            for rh in range(10, 100, 10):
                dp = api.calculate_dew_point(float(temp), float(rh))
                assert dp <= temp + 0.1, (
                    f"Dew point {dp} exceeds air temp {temp} at RH={rh}%"
                )

    def test_humidity_clamped_at_boundaries(self, api):
        """Extreme RH inputs (0, 101) should not raise and return sensible values."""
        dp_zero = api.calculate_dew_point(20.0, 0.0)
        dp_over = api.calculate_dew_point(20.0, 101.0)
        # Both should be finite floats, not NaN / inf
        assert isinstance(dp_zero, float)
        assert isinstance(dp_over, float)
        import math
        assert math.isfinite(dp_zero)
        assert math.isfinite(dp_over)

    def test_classify_heat_stress_levels(self, api):
        """Spot-check heat stress classification boundaries."""
        # dew > 24 → EXTREME
        status, _ = api.classify_heat_stress(25.0)
        assert "EXTREME" in status
        # dew < 8 → DRY/COLD
        status, _ = api.classify_heat_stress(5.0)
        assert "DRY" in status or "COLD" in status

    def test_current_conditions_has_required_keys(self, api):
        cond = api.get_current_conditions()
        for key in ("temp_c", "humidity", "dew_point", "heat_stress", "recommendation"):
            assert key in cond, f"Missing key: {key}"


# ══════════════════════════════════════════════════════════════════════════════
# 9. WEATHER WINDOW SELECTION — edge cases (ADR 0004)
# ══════════════════════════════════════════════════════════════════════════════

def _make_forecast(hours: list[int], date_str: str) -> list[dict]:
    """
    Build a minimal synthetic hourly forecast list for testing.

    Each entry contains the keys WeatherAPI.find_optimal_training_windows()
    actually reads: 'timestamp', 'hour', 'dew_point', 'temp_c'.
    All weather values are deliberately neutral (dew=10, temp=15) so
    scoring differences come purely from the time-of-day bonus/penalty.
    """
    return [
        {
            "timestamp": f"{date_str}T{h:02d}:00:00",
            "hour": h,
            "dew_point": 10.0,
            "temp_c": 15.0,
        }
        for h in hours
    ]


class TestWeatherWindows:
    """
    Unit tests for WeatherAPI.find_optimal_training_windows().

    Uses a monkeypatched get_hourly_forecast() so no network calls are made
    and the day's forecast is fully deterministic.
    """

    @pytest.fixture
    def patched_api(self, api, monkeypatch):
        """
        Return a WeatherAPI whose get_hourly_forecast() yields a
        synthetic 24-hour forecast for today.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        synthetic = _make_forecast(list(range(24)), today)
        monkeypatch.setattr(api, "get_hourly_forecast", lambda hours: synthetic)
        return api

    # ── guard / invalid input ───────────────────────────────────────────────

    def test_zero_duration_returns_empty(self, patched_api):
        result = patched_api.find_optimal_training_windows(duration_hours=0)
        assert result == []

    def test_negative_duration_returns_empty(self, patched_api):
        result = patched_api.find_optimal_training_windows(duration_hours=-1)
        assert result == []

    # ── slot count / boundary ───────────────────────────────────────────────

    def test_integer_duration_slots(self, patched_api):
        """duration_hours=1.0 → each window covers exactly 1 slot."""
        result = patched_api.find_optimal_training_windows(duration_hours=1.0)
        # 24 hours, 1 slot per window → 24 windows
        assert len(result) == 24

    def test_fractional_duration_ceiling(self, patched_api):
        """duration_hours=1.5 → ceil=2 slots per window → 22 windows (24-2)."""
        result = patched_api.find_optimal_training_windows(duration_hours=1.5)
        assert len(result) == 23   # 24 - ceil(1.5) = 24 - 2 = 22... wait, 24-2+1=23
        # windows start at hours 0..22 (23 windows); hour 23 would need slot 23+1=24 (OOB)

    def test_two_hour_duration_boundary(self, patched_api):
        """duration_hours=2.0 → ceil=2 slots → 23 windows (start hours 0-22)."""
        result = patched_api.find_optimal_training_windows(duration_hours=2.0)
        assert len(result) == 23

    def test_full_day_duration(self, patched_api):
        """duration_hours=24.0 → only 1 window (the whole day)."""
        result = patched_api.find_optimal_training_windows(duration_hours=24.0)
        assert len(result) == 1

    def test_duration_exceeding_day_returns_empty(self, patched_api):
        """duration_hours=25 → no window fits in 24-slot day."""
        result = patched_api.find_optimal_training_windows(duration_hours=25)
        assert result == []

    # ── sparse day / midnight boundary ──────────────────────────────────────

    def test_sparse_forecast_respects_boundary(self, api, monkeypatch):
        """With only 3 hours available, a 2-hour run yields exactly 2 windows."""
        today = datetime.now().strftime("%Y-%m-%d")
        sparse = _make_forecast([6, 7, 8], today)
        monkeypatch.setattr(api, "get_hourly_forecast", lambda hours: sparse)
        result = api.find_optimal_training_windows(duration_hours=2.0)
        assert len(result) == 2   # windows [6-7] and [7-8]

    def test_single_slot_forecast_1h(self, api, monkeypatch):
        """1 slot available, duration=1 → exactly 1 window."""
        today = datetime.now().strftime("%Y-%m-%d")
        monkeypatch.setattr(api, "get_hourly_forecast",
                            lambda hours: _make_forecast([6], today))
        result = api.find_optimal_training_windows(duration_hours=1.0)
        assert len(result) == 1

    def test_single_slot_forecast_2h(self, api, monkeypatch):
        """1 slot available, duration=2 → no window fits → empty."""
        today = datetime.now().strftime("%Y-%m-%d")
        monkeypatch.setattr(api, "get_hourly_forecast",
                            lambda hours: _make_forecast([6], today))
        result = api.find_optimal_training_windows(duration_hours=2.0)
        assert result == []

    # ── result structure ────────────────────────────────────────────────────

    def test_window_has_required_keys(self, patched_api):
        result = patched_api.find_optimal_training_windows(duration_hours=1.0)
        assert result, "Expected at least one window"
        required = {"start_time", "start_hour", "avg_dew_point", "avg_temp",
                    "score", "quality"}
        for key in required:
            assert key in result[0], f"Missing key '{key}' in window dict"

    def test_windows_sorted_best_first(self, patched_api):
        """Returned list must be sorted ascending by score (best = lowest score)."""
        result = patched_api.find_optimal_training_windows(duration_hours=1.0)
        scores = [w["score"] for w in result]
        assert scores == sorted(scores), "Windows are not sorted by score"

    # ── tie-breaking stability ───────────────────────────────────────────────

    def test_tie_sort_stable(self, api, monkeypatch):
        """
        When two windows have identical scores they must still appear in the
        result (no window lost) and the list stays sorted.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        # hours 8 and 9 both outside bonus/penalty bands → same base score
        two_hours = _make_forecast([8, 9, 10], today)
        monkeypatch.setattr(api, "get_hourly_forecast", lambda hours: two_hours)
        result = api.find_optimal_training_windows(duration_hours=1.0)
        assert len(result) == 3
        scores = [w["score"] for w in result]
        assert scores == sorted(scores)


# ══════════════════════════════════════════════════════════════════════════════
# TSB Engine — cold-start regression tests (ADR 0006)
# ══════════════════════════════════════════════════════════════════════════════

class TestTSBColdStart:
    """
    Guard removed: engine must work with ≥ 1 load record (not ≥ 7 / ≥ 3).
    Regression against the < 7 / < 3 minimum-record guards that caused
    INSUFFICIENT DATA on fresh installs and the first weeks after deployment.
    """

    @pytest.fixture
    def engine(self):
        from titan.science.tsb_engine import TSBEngine
        return TSBEngine()

    def test_zero_loads_returns_none(self, engine):
        """Engine with no data must return None for both CTL and ATL."""
        assert engine.calculate_ctl() is None
        assert engine.calculate_atl() is None

    def test_zero_loads_tsb_returns_none(self, engine):
        """calculate_tsb() returns (None, 'INSUFFICIENT DATA') with no loads."""
        val, status = engine.calculate_tsb()
        assert val is None
        assert status == "INSUFFICIENT DATA"

    def test_single_load_returns_float(self, engine):
        """One load record must be enough to produce a numeric CTL and ATL."""
        engine.add_daily_load("2026-01-01", 80.0)
        assert isinstance(engine.calculate_ctl(), float)
        assert isinstance(engine.calculate_atl(), float)

    def test_single_load_tsb_not_none(self, engine):
        """calculate_tsb() must return a numeric value with just 1 record."""
        engine.add_daily_load("2026-01-01", 80.0)
        val, status = engine.calculate_tsb()
        assert val is not None
        assert status != "INSUFFICIENT DATA"

    def test_three_loads_returns_float(self, engine):
        """Three load records (previous ATL threshold) must now produce a result."""
        for i, load in enumerate([70.0, 80.0, 75.0]):
            engine.add_daily_load(f"2026-01-0{i+1}", load)
        assert isinstance(engine.calculate_ctl(), float)
        assert isinstance(engine.calculate_atl(), float)

    def test_zero_tsb_treated_as_race_form(self, engine):
        """
        TSB = 0.0 must be returned as 0.0 (race form), not treated as falsy.
        Seeds CTL = ATL = same value → TSB = 0.0 exactly.
        """
        engine.add_daily_load("2026-01-01", 50.0)
        val, _ = engine.calculate_tsb()
        # With one load, CTL = ATL = seed value → TSB = 0.0
        assert val == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# TSB Engine — startup hydration integration test (ADR 0006)
# ══════════════════════════════════════════════════════════════════════════════

class TestTSBHydration:
    """
    Verify that clear() + add_daily_load() pattern used in _feed_load_engines()
    and _hydrate_engines_from_db() produces correct CTL/ATL after reload.
    """

    @pytest.fixture
    def engine(self):
        from titan.science.tsb_engine import TSBEngine
        return TSBEngine()

    def test_clear_then_reload_gives_correct_ctl(self, engine):
        """Clearing loads and reloading must not double-count sessions."""
        loads = [("2026-01-01", 60.0), ("2026-01-02", 70.0), ("2026-01-03", 80.0)]
        for date, load in loads:
            engine.add_daily_load(date, load)
        ctl_first = engine.calculate_ctl()

        # Simulate reload (as _feed_load_engines does)
        engine.daily_loads.clear()
        for date, load in loads:
            engine.add_daily_load(date, load)
        ctl_reload = engine.calculate_ctl()

        assert ctl_first == ctl_reload, "CTL changed after clear+reload — double-counting bug"

    def test_double_hydrate_does_not_drift(self, engine):
        """Calling hydration twice must produce the same TSB each time."""
        loads = [("2026-01-01", 50.0), ("2026-01-02", 60.0)]
        for _ in range(2):
            engine.daily_loads.clear()
            for date, load in loads:
                engine.add_daily_load(date, load)
        val1, _ = engine.calculate_tsb()

        engine.daily_loads.clear()
        for date, load in loads:
            engine.add_daily_load(date, load)
        val2, _ = engine.calculate_tsb()

        assert val1 == val2, "TSB drifted between identical hydration calls"


# ══════════════════════════════════════════════════════════════════════════════
# WeeklyPlanGenerator — None / 0.0 TSB null-safety (ADR 0006)
# ══════════════════════════════════════════════════════════════════════════════

class TestWeeklyPlannerNullSafety:
    """
    Regression for the tsb_value falsy bug:
      'readiness': 'GOOD' if ... and tsb_value and tsb_value > -20 ...
    When TSB = 0.0 (race form), the old guard treated it as False.
    """

    @pytest.fixture
    def planner(self):
        from titan.science.tsb_engine import TSBEngine
        from titan.science.hrv_engine import HRVGuidedEngine
        from titan.science.acwr_engine import ACWREngine
        from titan.features.weekly_planner import WeeklyPlanGenerator
        return WeeklyPlanGenerator(
            hrv_engine=HRVGuidedEngine(),
            tsb_engine=TSBEngine(),
            acwr_engine=ACWREngine(),
        )

    # Minimal session stub that passes the empty-guard and has low drift
    _SESSIONS = [{"session_type": "EASY", "distance_km": 10.0, "drift_pct": 1.0}]

    def test_none_tsb_does_not_raise(self, planner, monkeypatch):
        """analyze_past_week() must not raise when TSB returns None."""
        monkeypatch.setattr(
            planner.tsb_engine, "calculate_tsb", lambda: (None, "INSUFFICIENT DATA")
        )
        result = planner.analyze_past_week(sessions=self._SESSIONS)
        assert result["readiness"] == "COMPROMISED"

    def test_zero_tsb_gives_good_readiness(self, planner, monkeypatch):
        """TSB = 0.0 (race form) must yield GOOD readiness, not COMPROMISED."""
        monkeypatch.setattr(
            planner.tsb_engine, "calculate_tsb", lambda: (0.0, "🎯 RACE FORM")
        )
        result = planner.analyze_past_week(sessions=self._SESSIONS)
        assert result["readiness"] == "GOOD", (
            "TSB=0.0 must not be treated as falsy — use 'is not None' comparison"
        )
