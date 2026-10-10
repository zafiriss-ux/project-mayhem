"""SV-06 / ADR-0051: a missing resting HR or sleep score reaches governance as missing.

Before D-050 the morning sent governance a resting HR of 50 and a sleep score of 50 when
Garmin had none, so the H3 gate compared a made-up value and never applied the ADR-0051
EASY ceiling.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from titan.core.database import DatabaseManager
from titan.features.nutrition_optimizer import NutritionOptimizer
from titan.features.optimal_time_calculator import OptimalTimeCalculator
from titan.features.weekly_planner import WeeklyPlanGenerator
from titan.integrations.garmin_sync import GarminSync
from titan.integrations.telegram_bot import TitanTelegramBot
from titan.integrations.weather_api import WeatherAPI
from titan.orchestration.daily_coach import DailyCoach
from titan.orchestration.engine_registry import EngineRegistry
from titan.science.acwr_engine import ACWREngine
from titan.science.data_trust import evaluate_garmin_trust
from titan.science.glycogen_model import GlycogenModel

_TEMPO = {"session_type": "TEMPO", "duration_min": 60, "phase": "BUILD"}


def _coach(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DailyCoach:
    db = DatabaseManager("titan_core.db", db_dir=tmp_path)
    engines = EngineRegistry.from_db(db=db, athlete_id="owner")
    weather_api = WeatherAPI()
    coach = DailyCoach(
        garmin_sync=GarminSync(),
        weather_api=weather_api,
        telegram_bot=TitanTelegramBot(db=db),
        hrv_engine=engines.hrv,
        tsb_engine=engines.tsb,
        readiness_engine=engines.readiness,
        optimal_time_calc=OptimalTimeCalculator(weather_api),
        nutrition_optimizer=NutritionOptimizer(GlycogenModel()),
        weekly_planner=WeeklyPlanGenerator(engines.hrv, engines.tsb, ACWREngine()),
        db=db,
        athlete_id="owner",
        engines=engines,
    )
    monkeypatch.setattr(coach.weekly_planner, "get_today_session", lambda: dict(_TEMPO))
    # Past the override-lockdown cold start, so governance alone would keep TEMPO.
    monkeypatch.setattr(coach.db, "get_override_ratio", lambda days=14: 0.0)
    # Tonight's HRV is present, so only the reading under test is missing (D-048).
    coach.hrv.add_hrv_measurement(datetime.now(UTC).strftime("%Y-%m-%d"), 60.0)
    return coach


def _run(coach: DailyCoach, *, today_rhr: int, today_sleep_score: int | None):
    trust = evaluate_garmin_trust(data_age_hours=1.0)
    seen: list[dict] = []
    apply = coach.governance.apply_constraints

    def _spy(session_plan, context):
        seen.append(dict(context))
        return apply(session_plan=session_plan, context=context)

    coach.governance.apply_constraints = _spy
    result = coach._decision_pipeline(
        garmin_data={"activities": [], "weight": [], "sleep": [], "hrv": []},
        soreness=0,
        subjective_fatigue_score=0,
        today_rhr=today_rhr,
        today_sleep_score=today_sleep_score,
        today_sleep_hours=8.0,
        baseline_rhr_for_comparison=50.0,
        persistence_degraded=False,
        garmin_data_stale=False,
        latest_hrv=60.0,
        baseline_hrv=60.0,
        hrv_summary={},
        afi_final=1.0,
        afi_constraints={},
        tsb_value=5.0,
        tsb_status="NOMINAL",
        cs_thermal=None,
        garmin_trust=trust,
        garmin_report_payload={k: v for k, v in trust.to_payload().items() if k != "checked_at"},
        startup_hydration_confidence={},
        startup_confidence_applies=False,
    )
    return result, seen[-1]


@pytest.mark.integration
def test_measured_rhr_and_sleep_keep_the_planned_session(tmp_path, monkeypatch) -> None:
    result, context = _run(_coach(tmp_path, monkeypatch), today_rhr=50, today_sleep_score=85)
    assert result.session_plan["session_type"] == "TEMPO"
    assert (context["today_rhr"], context["sleep_score"]) == (50, 85)


@pytest.mark.integration
def test_missing_rhr_puts_an_easy_ceiling_on_quality_work(tmp_path, monkeypatch) -> None:
    result, context = _run(_coach(tmp_path, monkeypatch), today_rhr=0, today_sleep_score=85)
    assert context["today_rhr"] is None
    assert result.session_plan["session_type"] == "EASY"


@pytest.mark.integration
def test_missing_sleep_score_reaches_governance_as_missing(tmp_path, monkeypatch) -> None:
    _result, context = _run(_coach(tmp_path, monkeypatch), today_rhr=50, today_sleep_score=None)
    assert context["sleep_score"] is None
