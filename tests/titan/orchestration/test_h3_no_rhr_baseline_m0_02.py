"""M0-02: no RHR in the 7 days before today is a missing H3 baseline, not a CLEAR H3.

Before the fix the morning compared today's RHR with itself (delta 0), so H3 could never
fire and the rationale wrote CLEAR. Example from the Phase 0 report: a new athlete, or a
watch not worn for 7 nights, wakes with RHR 72 against a usual 55 and does TEMPO. Now the
missing baseline reaches governance as None and ADR-0051 applies, as for a missing HRV
baseline (D-105): EASY ceiling, lock DATA_MISSING_CONSERVATIVE_H3, rationale UNKNOWN.
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
    monkeypatch.setattr(coach.db, "get_override_ratio", lambda *, athlete_id, days=14: 0.0)
    # Tonight's HRV and its baseline are present: only the RHR baseline is under test.
    coach.hrv.add_hrv_measurement(datetime.now(UTC).strftime("%Y-%m-%d"), 60.0)
    return coach


def _run(coach: DailyCoach, *, today_rhr: int, baseline_rhr: float | None):
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
        today_sleep_score=85,
        today_sleep_hours=8.0,
        baseline_rhr_for_comparison=baseline_rhr,
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


def _locks(result) -> list[str]:
    return list(result.session_plan.get("governance_locks_applied") or [])


@pytest.mark.integration
def test_no_rhr_baseline_puts_an_easy_ceiling_on_quality_work(tmp_path, monkeypatch) -> None:
    """RHR 72 with no earlier RHR: EASY, never the planned TEMPO."""
    result, context = _run(_coach(tmp_path, monkeypatch), today_rhr=72, baseline_rhr=None)
    assert context["baseline_rhr"] is None
    assert result.session_plan["session_type"] == "EASY"
    assert "DATA_MISSING_CONSERVATIVE_H3" in _locks(result)


@pytest.mark.integration
def test_no_rhr_baseline_is_unknown_in_the_rationale_not_clear(tmp_path, monkeypatch) -> None:
    result, _context = _run(_coach(tmp_path, monkeypatch), today_rhr=72, baseline_rhr=None)
    findings = result.session_plan["decision_rationale"]["gate_findings"]
    h3 = next(f for f in findings if f["gate"] == "H3")
    assert h3["status"] == "UNKNOWN"


@pytest.mark.integration
def test_a_real_baseline_still_lets_h3_stop_a_spike(tmp_path, monkeypatch) -> None:
    """Unchanged: 72 against a baseline of 55 is a hard stop."""
    result, _context = _run(_coach(tmp_path, monkeypatch), today_rhr=72, baseline_rhr=55.0)
    assert result.session_plan["session_type"] == "REST"


@pytest.mark.integration
def test_a_real_baseline_without_a_spike_keeps_the_planned_session(tmp_path, monkeypatch) -> None:
    """Unchanged: a measured baseline and no spike keep TEMPO and add no H3 lock."""
    result, context = _run(_coach(tmp_path, monkeypatch), today_rhr=72, baseline_rhr=71.0)
    assert context["baseline_rhr"] == 71.0
    assert result.session_plan["session_type"] == "TEMPO"
    assert "DATA_MISSING_CONSERVATIVE_H3" not in _locks(result)
