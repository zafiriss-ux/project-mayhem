"""Tests for Opus audit fixes: pace_backfill guard, thread safety, EngineRegistry.from_db,
AthleteCoachingContext.engines wiring (Findings #1, #5, #8, #9)."""
from __future__ import annotations

import threading
import time

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration.engine_registry import EngineRegistry


@pytest.mark.unit
def test_pace_backfill_skips_when_no_nulls(tmp_path):
    db = DatabaseManager(str(tmp_path / "titan_core.db"))
    db.conn.execute(
        "INSERT INTO training_log "
        "(date, session_type, distance_km, duration_sec, avg_pace_sec_per_km, athlete_id) "
        "VALUES ('2026-01-01','EASY',10,3600,360,'owner')"
    )
    db.conn.commit()
    cursor = db.conn.cursor()
    t0 = time.monotonic()
    db._apply_v19_pace_backfill(cursor)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.1


@pytest.mark.integration
def test_hydrate_engines_thread_safe(tmp_path):
    from unittest.mock import MagicMock

    from titan.orchestration.daily_coach import DailyCoach

    db = DatabaseManager(str(tmp_path / "titan_core.db"))
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = db
    coach._routine_mutex = threading.RLock()

    # Minimal engine stubs — all accesses inside _hydrate_engines_from_db_locked
    # are wrapped in try/except so AttributeErrors are swallowed.  We use real-ish
    # mocks here so the method can reach further into its body.
    hrv = MagicMock()
    hrv.hrv_log = []
    coach.hrv = hrv
    tsb = MagicMock()
    tsb.daily_loads = {}
    coach.tsb = tsb
    nutrition = MagicMock()
    coach.nutrition = nutrition
    autonomic = MagicMock()
    coach.autonomic = autonomic
    cs_tracker = MagicMock()
    cs_tracker.confidence = 0.0
    cs_tracker.archetype = "UNKNOWN"
    cs_tracker.cs_smoothed = None
    coach.cs_tracker = cs_tracker

    errors: list[Exception] = []

    def hydrate():
        try:
            coach._hydrate_engines_from_db()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=hydrate)
    t2 = threading.Thread(target=hydrate)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert errors == [], f"Thread safety violations: {errors}"


@pytest.mark.unit
def test_engine_registry_from_db_callable(tmp_path):
    from titan.science.tsb_engine import TSBEngine

    db = DatabaseManager(str(tmp_path / "titan_core.db"))
    registry = EngineRegistry.from_db(db)
    assert isinstance(registry, EngineRegistry)
    assert isinstance(registry.tsb, TSBEngine)


@pytest.mark.unit
def test_athlete_coaching_context_receives_engines(tmp_path):
    from unittest.mock import MagicMock

    from titan.orchestration.coaching_pipeline import AthleteCoachingContext

    db = DatabaseManager(str(tmp_path / "titan_core.db"))
    engines = EngineRegistry.from_db(db)

    garmin_data = {
        "activities": [],
        "weight": [],
        "sleep": [],
        "hrv": [],
        "hrv_sync_metrics": {"days_back": 0, "synced_days": 0, "skipped_days": 0},
    }

    coach = MagicMock()
    ctx = AthleteCoachingContext(
        athlete_id="owner",
        coach=coach,
        db=db,
        garmin_data=garmin_data,
        soreness=0,
        subjective_fatigue_score=0,
        today_rhr=50,
        today_sleep_score=80,
        today_sleep_hours=8.0,
        baseline_rhr_for_comparison=50.0,
        persistence_degraded=False,
        garmin_data_stale=False,
        latest_hrv=60.0,
        baseline_hrv=60.0,
        hrv_summary={},
        afi_final=1.0,
        afi_constraints={},
        tsb_value=0.0,
        tsb_status="NOMINAL",
        cs_thermal=None,
        garmin_trust=None,
        garmin_report_payload={},
        startup_hydration_confidence={},
        startup_confidence_applies=False,
        engines=engines,
    )
    assert ctx.engines is not None
    assert isinstance(ctx.engines, EngineRegistry)
