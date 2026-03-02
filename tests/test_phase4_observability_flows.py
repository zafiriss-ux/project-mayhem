import json
import logging
from unittest.mock import MagicMock

from titan.features.nutrition_optimizer import NutritionOptimizer
from titan.features.weekly_planner import WeeklyPlanGenerator
from titan.science.readiness_engine import ReadinessEngine


def _json_messages(caplog):
    messages = []
    for record in caplog.records:
        try:
            messages.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            continue
    return messages


def test_readiness_emits_structured_event(caplog):
    caplog.set_level(logging.INFO)

    result = ReadinessEngine.analyze_readiness(
        today_hrv=48,
        baseline_hrv=60,
        today_rhr=58,
        baseline_rhr=50,
        sleep_score=55,
        soreness=8,
    )

    assert result["status"] == "🛑 POOR"
    events = _json_messages(caplog)
    readiness = [e for e in events if e.get("flow") == "readiness" and e.get("action") == "computed"]
    assert readiness
    assert readiness[0]["score"] == result["score"]
    assert readiness[0]["components"]["hrv"] == 20


def test_weekly_planner_emits_generation_events(caplog):
    caplog.set_level(logging.INFO)

    hrv_engine = MagicMock()
    hrv_engine.get_hrv_summary.return_value = {"baseline": 60, "latest_hrv": 58}
    hrv_engine.get_trend_analysis.return_value = {"trend": "STABLE"}

    tsb_engine = MagicMock()
    tsb_engine.calculate_tsb.return_value = (-12.0, "MANAGEABLE")

    acwr_engine = MagicMock()

    planner = WeeklyPlanGenerator(hrv_engine=hrv_engine, tsb_engine=tsb_engine, acwr_engine=acwr_engine)

    plan = planner.generate_weekly_plan(athlete_profile={"threshold_hr": 168}, phase="BUILD")
    assert plan["phase"] == "BUILD"

    events = _json_messages(caplog)
    started = [e for e in events if e.get("flow") == "weekly_planner" and e.get("action") == "plan_generation_started"]
    generated = [e for e in events if e.get("flow") == "weekly_planner" and e.get("action") == "plan_generated"]

    assert started
    assert generated
    assert generated[0]["weekly_km"] == plan["total_km"]


def test_nutrition_emits_weight_and_plan_events(caplog):
    caplog.set_level(logging.INFO)

    optimizer = NutritionOptimizer(glycogen_model=MagicMock())
    for i in range(7):
        optimizer.add_weight_entry(f"2026-03-{i+1:02d}", 75.0 - (i * 0.1))

    plan = optimizer.calculate_daily_nutrition(
        weight_kg=74.4,
        today_session={"session_type": "TEMPO", "duration_min": 70, "dew_point": 19},
        training_phase="BUILD",
    )

    assert plan["total_calories"] > 0

    events = _json_messages(caplog)
    weight_events = [e for e in events if e.get("flow") == "nutrition" and e.get("action") == "weight_trend_analyzed"]
    plan_events = [e for e in events if e.get("flow") == "nutrition" and e.get("action") == "daily_plan_calculated"]

    assert weight_events
    assert plan_events
    assert plan_events[0]["weight_status"] == plan["weight_trend"]["status"]
