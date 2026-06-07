from __future__ import annotations

import pytest

from tests.e2e.conftest import (
    StubGarminSync,
    StubGlycogen,
    StubGovernance,
    StubNutrition,
    StubOptimalTime,
    StubOutcomeTracker,
    StubReadiness,
    StubSimpleEngine,
    StubTelegram,
    StubTSB,
    StubVLG,
    StubWeather,
    StubWeeklyPlanner,
    stub_engine_registry,
)
from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DailyCoach


@pytest.mark.integration
def test_idempotency_replay_garmin_day_persisted_twice(tmp_path):
    fixed_today = "2026-03-04"
    db = DatabaseManager(db_name="e2e_idempotency_replay.db", db_dir=tmp_path)

    coach = DailyCoach(
        garmin_sync=StubGarminSync(today=fixed_today),
        weather_api=StubWeather(),
        telegram_bot=StubTelegram(),
        hrv_engine=StubSimpleEngine(),
        tsb_engine=StubTSB(),
        readiness_engine=StubReadiness(),
        optimal_time_calc=StubOptimalTime(),
        nutrition_optimizer=StubNutrition(),
        weekly_planner=StubWeeklyPlanner(),
        db=db,
        engines=stub_engine_registry(),
        glycogen_accum=StubGlycogen(),
        governance=StubGovernance(),
        volume_load_gauge=StubVLG(),
        outcome_tracker=StubOutcomeTracker(),
    )

    try:
        assert coach.run_morning_routine() is True

        training_log_count_after_first = db.conn.execute(
            "SELECT COUNT(*) FROM training_log WHERE date = ?", (fixed_today,)
        ).fetchone()[0]
        daily_metrics_count_after_first = db.conn.execute(
            "SELECT COUNT(*) FROM daily_metrics WHERE date = ?", (fixed_today,)
        ).fetchone()[0]
        ctl_atl_tsb_after_first = db.get_ctl_atl_tsb()

        assert coach.run_morning_routine() is True

        training_log_count_after_second = db.conn.execute(
            "SELECT COUNT(*) FROM training_log WHERE date = ?", (fixed_today,)
        ).fetchone()[0]
        daily_metrics_count_after_second = db.conn.execute(
            "SELECT COUNT(*) FROM daily_metrics WHERE date = ?", (fixed_today,)
        ).fetchone()[0]
        ctl_atl_tsb_after_second = db.get_ctl_atl_tsb()

        assert training_log_count_after_first == training_log_count_after_second
        assert daily_metrics_count_after_first == daily_metrics_count_after_second
        assert ctl_atl_tsb_after_first == ctl_atl_tsb_after_second
    finally:
        db.close()
