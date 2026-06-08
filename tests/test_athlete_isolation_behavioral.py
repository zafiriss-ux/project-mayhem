"""P27-B4: Behavioral two-athlete isolation fitness function.

Verifies that DailyCoach hydrates the correct athlete's data and that
two athletes do not contaminate each other's engine state. Behavioral
complement to the static AST lint in test_athlete_isolation_invariant.py.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
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
from titan.science.glycogen_model import GlycogenModel


def _make_coach(db: DatabaseManager, athlete_id: str) -> DailyCoach:
    """Build a minimal DailyCoach for the given athlete_id."""
    engines = EngineRegistry.from_db(db=db, athlete_id=athlete_id)
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
        athlete_id=athlete_id,
        engines=engines,
    )


@pytest.mark.integration
def test_two_athletes_have_distinct_tsb_state() -> None:
    """P27-B4: Two athletes with different training loads must have
    different TSB state after hydration — no cross-athlete contamination.

    Behavioral complement to test_athlete_isolation_invariant.py (static AST).
    Closes FMEA F26-02 false-mitigation gap (Opus pre-Phase-27 audit A4-02).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db = DatabaseManager("iso_test.db", db_dir=Path(tmpdir))

        # Seed athlete A and B in the athletes table
        db.conn.execute(
            "INSERT OR IGNORE INTO athletes "
            "(athlete_id, display_name, created_at, is_cold_start) "
            "VALUES ('athlete_a', 'Athlete A', datetime('now'), 0)"
        )
        db.conn.execute(
            "INSERT OR IGNORE INTO athletes "
            "(athlete_id, display_name, created_at, is_cold_start) "
            "VALUES ('athlete_b', 'Athlete B', datetime('now'), 0)"
        )
        db.conn.commit()

        # Seed distinct training loads for each athlete (within the
        # CTL lookback window — must be relative to "now", not fixed dates).
        today = datetime.now(UTC)
        for i in range(10):
            date = (today - timedelta(days=i + 1)).strftime("%Y-%m-%d")
            db.save_session(
                date=date, session_type="EASY",
                distance_km=10.0, duration_sec=3600,
                avg_hr=140, max_hr=155, rpe=5,
                training_load=50,    # athlete_a: low load
                athlete_id="athlete_a",
            )
            db.save_session(
                date=date, session_type="INTERVALS",
                distance_km=10.0, duration_sec=3600,
                avg_hr=165, max_hr=180, rpe=9,
                training_load=150,   # athlete_b: high load
                athlete_id="athlete_b",
            )

        coach_a = _make_coach(db, "athlete_a")
        coach_b = _make_coach(db, "athlete_b")

        # TSB engines must reflect their respective loads
        tsb_a = coach_a.engines.tsb
        tsb_b = coach_b.engines.tsb

        ctl_a = tsb_a.calculate_ctl()
        ctl_b = tsb_b.calculate_ctl()

        assert ctl_a is not None and ctl_b is not None, (
            "Both athletes should have non-None CTL after training sessions"
        )
        assert ctl_a != ctl_b, (
            f"Cross-athlete contamination detected: athlete_a CTL={ctl_a} "
            f"== athlete_b CTL={ctl_b}. DailyCoach is using the wrong "
            f"athlete's training data."
        )
        # athlete_b has 3x the load so must have higher CTL
        assert ctl_b > ctl_a, (
            f"athlete_b (load=150) should have higher CTL than "
            f"athlete_a (load=50). Got a={ctl_a}, b={ctl_b}"
        )

        db.close()


@pytest.mark.integration
def test_daily_metrics_two_athletes_same_date() -> None:
    """P27-B4 / A3-02: Two athletes can store daily_metrics for the
    same date without collision (UNIQUE on athlete_id+date, not date alone).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db = DatabaseManager("iso_dm_test.db", db_dir=Path(tmpdir))

        db.save_daily_metric(date="2026-06-01", hrv=55.0, athlete_id="athlete_a")
        db.save_daily_metric(date="2026-06-01", hrv=72.0, athlete_id="athlete_b")

        rows = db.conn.execute(
            "SELECT athlete_id, hrv_rmssd FROM daily_metrics "
            "WHERE date='2026-06-01' ORDER BY athlete_id"
        ).fetchall()

        assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}: {rows}"
        assert rows[0] == ("athlete_a", 55.0)
        assert rows[1] == ("athlete_b", 72.0)

        db.close()
