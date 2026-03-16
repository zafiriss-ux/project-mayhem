from titan.features.optimal_time_calculator import OptimalTimeCalculator
from titan.features.weekly_planner import WeeklyPlanGenerator
from titan.integrations.telegram_bot import TitanTelegramBot
from titan.orchestration.daily_coach import _compute_esi_context, _compute_esi_level
from titan.science.governance_engine import GovernanceEngine


class _StubWeatherAPI:
    def get_current_conditions(self):
        return {"data_quality": "live", "weather_confidence": "LIVE"}

    def find_optimal_training_windows(self, day_offset: int, duration_hours: float):
        return [
            {
                "start_time": "2026-03-04T06:00:00",
                "start_hour": 6,
                "avg_dew_point": 11.0,
                "avg_temp": 14.0,
                "score": 1,
                "quality": "🟩 EXCELLENT",
            }
        ]


class _FakeHRVEngine:
    def get_hrv_summary(self):
        return {"baseline": 60, "latest_hrv": 58}

    def get_trend_analysis(self):
        return {"trend": "stable"}


class _FakeTSBEngine:
    def calculate_tsb(self):
        return -2.0, "BALANCED"


class _FakeACWR:
    pass


def _base_context(**overrides):
    context = {
        "afi_constraints": {"afi_modifier": 0, "readiness_clamp": 100},
        "intensity_gate_result": {"zone": "GREEN"},
        "readiness_score": 80.0,
        "glycogen_debt": 1.0,
        "fatigue_level": "LOW",
        "acwr": 1.0,
        "days_since_last_vo2": 5,
        "fueling_confirmed": True,
        "planned_duration_min": 60,
        "today_hrv": 50.0,
        "baseline_hrv": 45.0,
        "hrv_std_dev": 2.0,
        "today_rhr": 52,
        "baseline_rhr": 50.0,
        "sleep_score": 80,
        "subjective_fatigue_score": 4,
        "tsb_value": 0.0,
        "injury_flag": False,
        "priority_vector": {},
        "lock_thresholds": {},
    }
    context.update(overrides)
    return context


def test_compute_esi_level_happy_path_extreme_due_to_dew_point():
    assert _compute_esi_level(dew_point_c=22.0, temp_c=26.0) == "EXTREME"


def test_compute_esi_level_boundary_low_below_moderate_threshold():
    assert _compute_esi_level(dew_point_c=14.9, temp_c=20.0) == "LOW"


def test_compute_esi_context_happy_path_returns_expected_adjustment():
    esi = _compute_esi_context({"dew_point": 18.0, "temp_c": 29.0})

    assert esi["esi_level"] == "HIGH"
    assert esi["esi_pace_adjustment_sec_per_km"] == 12


def test_compute_esi_context_boundary_missing_weather_defaults_to_low():
    esi = _compute_esi_context({})

    assert esi["esi_level"] == "LOW"
    assert esi["esi_pace_adjustment_sec_per_km"] == 0


def test_weekly_planner_apply_esi_adjustment_happy_path_adds_guidance():
    planner = WeeklyPlanGenerator(_FakeHRVEngine(), _FakeTSBEngine(), _FakeACWR())

    adjusted = planner.apply_esi_adjustment(
        {"session_type": "TEMPO", "details": "Steady run"},
        {"esi_level": "HIGH", "esi_pace_adjustment_sec_per_km": 12},
    )

    assert adjusted["esi_level"] == "HIGH"
    assert adjusted["esi_pace_adjustment_sec_per_km"] == 12
    assert "+12s/km" in adjusted["details"]


def test_weekly_planner_apply_esi_adjustment_boundary_rest_no_pace_note():
    planner = WeeklyPlanGenerator(_FakeHRVEngine(), _FakeTSBEngine(), _FakeACWR())

    adjusted = planner.apply_esi_adjustment(
        {"session_type": "REST", "details": "Recovery day"},
        {"esi_level": "EXTREME", "esi_pace_adjustment_sec_per_km": 20},
    )

    assert adjusted["esi_level"] == "EXTREME"
    assert adjusted["details"] == "Recovery day"


def test_optimal_time_includes_esi_fields_happy_path():
    calc = OptimalTimeCalculator(_StubWeatherAPI())

    result = calc.calculate_optimal_time(
        session_type="EASY",
        esi_level="HIGH",
        esi_pace_adjustment_sec_per_km=12,
    )

    assert result["esi_level"] == "HIGH"
    assert result["esi_pace_adjustment_sec_per_km"] == 12


def test_optimal_time_esi_fields_boundary_defaults_applied():
    calc = OptimalTimeCalculator(_StubWeatherAPI())

    result = calc.calculate_optimal_time(session_type="EASY")

    assert result["esi_level"] == "LOW"
    assert result["esi_pace_adjustment_sec_per_km"] == 0


def test_governance_vo2_blocked_when_esi_extreme_happy_path():
    engine = GovernanceEngine()
    session = {"session_type": "INTERVALS", "zone": 5, "max_zone": 5, "duration_min": 60}

    result = engine.apply_constraints(session_plan=session, context=_base_context(esi_level="EXTREME"))

    assert "VO2_ELIGIBILITY_GATE" in result.get("governance_locks_applied", [])
    assert result["session_type"] == "TEMPO"
    assert result["vo2_eligibility"]["eligible"] is False


def test_governance_vo2_not_blocked_when_esi_low_boundary():
    engine = GovernanceEngine()
    session = {"session_type": "INTERVALS", "zone": 5, "max_zone": 5, "duration_min": 60}

    result = engine.apply_constraints(session_plan=session, context=_base_context(esi_level="LOW"))

    assert result["vo2_eligibility"]["eligible"] is True


def test_telegram_daily_coaching_includes_esi_and_adjusted_pace_happy_path(monkeypatch):
    bot = TitanTelegramBot(bot_token="x", chat_id="123")
    sent = {}

    def _capture(message: str):
        sent["message"] = message
        return True

    monkeypatch.setattr(bot, "send_message", _capture)

    ok = bot.send_daily_coaching(
        {
            "session_type": "EASY",
            "duration": "8 km",
            "optimal_time": "06:00",
            "dew_point": 17,
            "conditions": "Warm",
            "hrv_status": "stable",
            "sleep_quality": 80,
            "readiness_score": 75,
            "nutrition_plan": "100g carbs",
            "esi_level": "HIGH",
            "esi_pace_adjustment_sec_per_km": 12,
        }
    )

    assert ok is True
    assert "*ESI:* HIGH" in sent["message"]
    assert "*Adjusted target pace:* +12s/km" in sent["message"]


def test_telegram_daily_coaching_boundary_no_adjusted_pace_line_when_zero(monkeypatch):
    bot = TitanTelegramBot(bot_token="x", chat_id="123")
    sent = {}

    def _capture(message: str):
        sent["message"] = message
        return True

    monkeypatch.setattr(bot, "send_message", _capture)

    bot.send_daily_coaching(
        {
            "session_type": "EASY",
            "duration": "8 km",
            "optimal_time": "06:00",
            "dew_point": 12,
            "conditions": "Pleasant",
            "hrv_status": "stable",
            "sleep_quality": 80,
            "readiness_score": 75,
            "nutrition_plan": "100g carbs",
            "esi_level": "LOW",
            "esi_pace_adjustment_sec_per_km": 0,
        }
    )

    assert "*ESI:* LOW" in sent["message"]
    assert "Adjusted target pace" not in sent["message"]
