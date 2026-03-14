from __future__ import annotations

from titan import main as titan_main
from titan.science.drift_engine import DriftEngine


class _TelegramHarness:
    def __init__(self) -> None:
        self.commands: dict[str, object] = {}

    def register_command(self, name, callback) -> None:
        self.commands[name] = callback


class _NoopDailyCoach:
    def __init__(self) -> None:
        self.outcome_tracker = self

    def run_morning_routine(self):
        return None

    def get_calibration_summary(self):
        return {"status": "NO_OUTCOMES_YET", "n_decisions": 0}


class _NoopPlanner:
    def generate_weekly_plan(self, athlete_profile, phase):
        return {"athlete": athlete_profile.get("name", "unknown"), "phase": phase}


class _NoopHRV:
    def get_hrv_summary(self):
        return {"baseline": 50, "trend": "STABLE", "latest_hrv": 50}


class _NoopTSB:
    ctl = 80.0
    atl = 72.0

    def calculate_tsb(self):
        return (8.0, "NEUTRAL")


class _NoopReadiness:
    def analyze_readiness(self, **_kwargs):
        return {"score": 70, "status": "OK", "recommendation": "Proceed"}


class _NoopNutrition:
    def analyze_weight_trend(self):
        return {"current_weight": 70.0}

    def calculate_daily_nutrition(self, **_kwargs):
        return {"carbs_g": 250, "protein_g": 120, "fat_g": 70, "total_calories": 2300}


class _NoopOptTime:
    def calculate_optimal_time(self, **_kwargs):
        return {"recommended_time": "07:00"}


class _GarminWithActivity:
    def sync_all(self):
        return {"activities": [], "weight": [], "hrv": [], "sleep": []}

    def sync_activities(self, days_back):
        assert days_back == 14
        return [{"avg_hr": 150, "duration_sec": 3600}]


class _NoopEquipment:
    def recommend_shoe(self, session_type):
        return f"Shoe for {session_type}"


def _make_ctx_with_real_drift_engine() -> dict[str, object]:
    return {
        "daily_coach": _NoopDailyCoach(),
        "weekly_planner": _NoopPlanner(),
        "athlete_profile": {"name": "Ada", "phase": "BUILD"},
        "hrv_engine": _NoopHRV(),
        "tsb_engine": _NoopTSB(),
        "readiness_engine": _NoopReadiness(),
        "nutrition_optimizer": _NoopNutrition(),
        "optimal_time_calc": _NoopOptTime(),
        "garmin": _GarminWithActivity(),
        "drift_engine": DriftEngine(),
        "equipment": _NoopEquipment(),
        "last_garmin_data": {},
        "today_session_type": "EASY",
    }


def test_register_telegram_callbacks_drift_command_accepts_real_drift_engine_instance():
    telegram = _TelegramHarness()
    titan_main._register_telegram_callbacks(telegram, _make_ctx_with_real_drift_engine())

    result = telegram.commands["drift"]()

    assert result.startswith("📉 *CARDIAC DRIFT*")
    assert "Assessment:" in result


def test_analyze_cardiac_drift_returns_expected_payload_for_split_halves():
    engine = DriftEngine()

    payload = engine.analyze_cardiac_drift(hr_data=[140, 142, 147, 149], duration_min=60)

    assert payload["drift_percent"] == 5.0
    assert payload["assessment"] == "POOR"
    assert payload["lt_zone"] == "ABOVE_LT"


def test_analyze_cardiac_drift_handles_insufficient_or_invalid_hr_data():
    engine = DriftEngine()

    payload = engine.analyze_cardiac_drift(hr_data=[150], duration_min=60)

    assert payload == {"drift_percent": 0.0, "assessment": "INSUFFICIENT_DATA", "lt_zone": "UNKNOWN"}


def test_compute_drift_zero_first_half_returns_zero_guard_value():
    assert DriftEngine.compute_drift(0.0, 150.0) == 0.0
