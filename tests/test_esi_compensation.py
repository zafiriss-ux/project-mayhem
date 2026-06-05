import pytest

from titan.features.optimal_time_calculator import OptimalTimeCalculator
from titan.features.weekly_planner import WeeklyPlanGenerator
from titan.orchestration.daily_coach import _compute_esi
from titan.science.governance_engine import GovernanceEngine


class _DummyEngine:
    def get_hrv_summary(self):
        return {"baseline": 40}

    def calculate_tsb(self):
        return 0.0, "NEUTRAL"


class _DummyWeather:
    def get_current_conditions(self):
        return {"data_quality": "synthetic", "weather_confidence": "SYNTHETIC"}


@pytest.mark.unit
def test_compute_esi_extreme_returns_highest_adjustment() -> None:
    level, pace_adjust = _compute_esi(temperature_c=30.0, dew_point_c=20.0)

    assert level == "EXTREME"
    assert pace_adjust == 25


@pytest.mark.unit
def test_compute_esi_boundary_low_returns_no_adjustment() -> None:
    level, pace_adjust = _compute_esi(temperature_c=10.0, dew_point_c=8.0)

    assert level == "LOW"
    assert pace_adjust == 0


@pytest.mark.unit
def test_weekly_planner_accepts_esi_context() -> None:
    planner = WeeklyPlanGenerator(_DummyEngine(), _DummyEngine(), _DummyEngine())

    session = planner.get_today_session(esi_level="HIGH", esi_pace_adjustment_sec_per_km=15)

    assert session["esi_level"] == "HIGH"
    assert session["esi_pace_adjustment_sec_per_km"] == 15


@pytest.mark.unit
def test_optimal_time_accepts_esi_context() -> None:
    calc = OptimalTimeCalculator(_DummyWeather())

    result = calc.calculate_optimal_time(
        session_type="EASY",
        esi_level="MODERATE",
        esi_pace_adjustment_sec_per_km=8,
    )

    assert result["esi_level"] == "MODERATE"
    assert result["esi_pace_adjustment_sec_per_km"] == 8


@pytest.mark.unit
def test_governance_blocks_vo2_when_esi_extreme() -> None:
    gov = GovernanceEngine()
    session_plan = {"session_type": "HAMMER", "zone": 5}
    context = {
        "acwr": 1.0,
        "readiness_score": 75,
        "glycogen_debt": 3.0,
        "fatigue_level": "LOW",
        "days_since_last_vo2": 3,
        "esi_level": "EXTREME",
    }

    result = gov._check_vo2_eligibility(session_plan, context)

    assert result is not None
    assert result["eligible"] is False
    assert "V4" in result["failed_conditions"]
    assert session_plan["session_type"] == "TEMPO"


@pytest.mark.unit
def test_governance_allows_vo2_when_esi_not_extreme() -> None:
    gov = GovernanceEngine()
    session_plan = {"session_type": "HAMMER", "zone": 5}
    context = {
        "acwr": 1.0,
        "readiness_score": 75,
        "glycogen_debt": 3.0,
        "fatigue_level": "LOW",
        "days_since_last_vo2": 3,
        "esi_level": "HIGH",
    }

    result = gov._check_vo2_eligibility(session_plan, context)

    assert result is not None
    assert result["eligible"] is True
    assert result["failed_conditions"] == []
    assert session_plan["session_type"] == "HAMMER"
