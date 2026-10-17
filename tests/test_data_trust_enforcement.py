"""INV-24 (T-PRA-24, B-14): a computed data-trust verdict is enforced.

When the data-trust arbitration yields INVALID, the coaching decision is
clamped to EASY (REST stays REST) through the same EASY / 45-minute ceiling
the Garmin staleness clamp uses. A verdict that is computed, logged and
ignored is forbidden.
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
from titan.orchestration.daily_coach import DailyCoach, _cap_session_for_invalid_trust
from titan.orchestration.engine_registry import EngineRegistry
from titan.science.acwr_engine import ACWREngine
from titan.science.data_trust import DataTrustLevel, evaluate_garmin_trust
from titan.science.glycogen_model import GlycogenModel

_INTERVALS = {"session_type": "INTERVALS", "duration_min": 70, "phase": "BUILD"}
_TEMPO = {"session_type": "TEMPO", "duration_min": 60, "phase": "BUILD"}


# ── Unit: the clamp itself ──────────────────────────────────────────────────


def test_invalid_trust_caps_hard_session_at_easy() -> None:
    capped, clamped = _cap_session_for_invalid_trust(
        dict(_INTERVALS), trust_level=DataTrustLevel.INVALID, reasons=["bounds_violation"], stage="t"
    )
    assert clamped is True
    assert capped["session_type"] == "EASY"
    assert capped["duration_min"] == 45
    assert capped["phase"] == "BUILD"


def test_invalid_trust_keeps_rest_as_rest() -> None:
    rest = {"session_type": "REST", "duration_min": 0}
    capped, clamped = _cap_session_for_invalid_trust(
        rest, trust_level=DataTrustLevel.INVALID, reasons=[], stage="t"
    )
    assert clamped is False
    assert capped["session_type"] == "REST"


@pytest.mark.parametrize("level", [DataTrustLevel.TRUSTED, DataTrustLevel.SUSPECT])
def test_valid_trust_leaves_session_unchanged(level: DataTrustLevel) -> None:
    session, clamped = _cap_session_for_invalid_trust(
        dict(_INTERVALS), trust_level=level, reasons=[], stage="t"
    )
    assert clamped is False
    assert session == _INTERVALS


# ── Behavioral: the decision pipeline honours an INVALID verdict ────────────


def _make_coach(tmp_path: Path) -> DailyCoach:
    db = DatabaseManager("titan_core.db", db_dir=tmp_path)
    engines = EngineRegistry.from_db(db=db, athlete_id="owner")
    weather_api = WeatherAPI()
    return DailyCoach(
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


def _run_pipeline(coach: DailyCoach, garmin_trust):
    report = {k: v for k, v in garmin_trust.to_payload().items() if k != "checked_at"}
    return coach._decision_pipeline(
        garmin_data={"activities": [], "weight": [], "sleep": [], "hrv": []},
        soreness=0,
        subjective_fatigue_score=0,
        today_rhr=50,
        today_sleep_score=85,
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
        garmin_trust=garmin_trust,
        garmin_report_payload=report,
        startup_hydration_confidence={},
        startup_confidence_applies=False,
    )


def _coach_planning_tempo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DailyCoach:
    coach = _make_coach(tmp_path)
    monkeypatch.setattr(coach.weekly_planner, "get_today_session", lambda: dict(_TEMPO))
    # Past the override-lockdown cold start, so governance alone would keep TEMPO.
    monkeypatch.setattr(coach.db, "get_override_ratio", lambda *, athlete_id, days=14: 0.0)
    # Tonight's HRV is present (D-048: a missing reading would cap the day at EASY).
    coach.hrv.add_hrv_measurement(datetime.now(UTC).strftime("%Y-%m-%d"), 60.0)
    return coach


@pytest.mark.integration
def test_invalid_verdict_clamps_the_coaching_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coach = _coach_planning_tempo(tmp_path, monkeypatch)
    # Fresh data (not stale), but the sync carried a bounds violation → INVALID.
    invalid = evaluate_garmin_trust(data_age_hours=1.0, quality_flags=["bounds_violation"])
    assert invalid.trust_level == DataTrustLevel.INVALID

    result = _run_pipeline(coach, invalid)

    assert result.session_plan["session_type"] == "EASY"
    assert int(result.session_plan["duration_min"]) <= 45
    assert result.decision_trace["data_trust_clamped"] is True
    assert result.decision_trace["session_post_governance"] == "EASY"


@pytest.mark.integration
def test_trusted_verdict_does_not_clamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coach = _coach_planning_tempo(tmp_path, monkeypatch)
    trusted = evaluate_garmin_trust(data_age_hours=1.0)

    result = _run_pipeline(coach, trusted)

    assert result.session_plan["session_type"] == "TEMPO"
    assert result.decision_trace["data_trust_clamped"] is False
