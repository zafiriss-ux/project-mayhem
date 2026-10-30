"""Athlete isolation of degraded mode, operator notes and manual entries (ISO-2..ISO-4, D-110).

Each test reproduces what the Phase 4 isolation audit found and fails without the fix:

- ISO-2: the degraded-mode timers were one shared set, so one athlete's stale Garmin
  alerted for another and a healthy morning cleared another athlete's timer;
- ISO-3: an operator note landed on whichever athlete's decision of the day came last;
- ISO-4: every athlete's pipeline read the owner's manual HRV and RHR.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from titan.core.database import SCHEMA_VERSION, DatabaseManager
from titan.integrations.biometric_router import ManualEntryAdapter
from titan.orchestration.daily_coach import DegradedModeTracker

A = "a-0000000a"
B = "a-0000000b"
TODAY = "2026-10-17"


def _db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager("titan_core.db", db_dir=tmp_path)


def _rows(db: DatabaseManager) -> list[tuple[str, str]]:
    return sorted(db.conn.execute("SELECT athlete_id, failure_type FROM degraded_mode_state").fetchall())


@pytest.mark.unit
def test_another_athletes_old_timer_does_not_alert_for_this_athlete(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        thirty_hours_ago = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
        db.upsert_degraded_mode_state("garmin_data_stale", thirty_hours_ago, athlete_id="owner")
        alerts: list[str] = []

        DegradedModeTracker(db=db, athlete_id=A).update({"garmin_data_stale": True}, alert_fn=alerts.append)

        assert alerts == [], "athlete A's first stale morning used the owner's 30-hour-old timer"
        assert _rows(db) == [(A, "garmin_data_stale"), ("owner", "garmin_data_stale")]
    finally:
        db.close()


@pytest.mark.unit
def test_a_healthy_athlete_does_not_clear_another_athletes_timer(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        DegradedModeTracker(db=db, athlete_id=A).update({"garmin_data_stale": True}, alert_fn=lambda _m: None)
        DegradedModeTracker(db=db, athlete_id=B).update({"garmin_data_stale": False}, alert_fn=lambda _m: None)

        assert _rows(db) == [(A, "garmin_data_stale")]
    finally:
        db.close()


@pytest.mark.unit
def test_each_athletes_own_old_timer_still_alerts(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        thirty_hours_ago = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
        db.upsert_degraded_mode_state("garmin_data_stale", thirty_hours_ago, athlete_id=A)
        alerts: list[str] = []

        DegradedModeTracker(db=db, athlete_id=A).update({"garmin_data_stale": True}, alert_fn=alerts.append)

        assert len(alerts) == 1 and "garmin_data_stale" in alerts[0]
    finally:
        db.close()


@pytest.mark.unit
def test_v33_gives_old_rows_to_the_owner_and_keys_by_athlete(tmp_path: Path) -> None:
    """A v32 database: 'default' rows become the owner's; the earlier timer of a pair wins."""
    db = _db(tmp_path)
    db.close()
    raw = sqlite3.connect(tmp_path / "titan_core.db")
    raw.executescript("""
        DROP TABLE degraded_mode_state;
        CREATE TABLE degraded_mode_state (
            failure_type TEXT PRIMARY KEY,
            degraded_since TEXT NOT NULL,
            athlete_id TEXT NOT NULL DEFAULT 'default'
        );
        INSERT INTO degraded_mode_state VALUES ('garmin_data_stale', '2026-10-15T07:00:00+00:00', 'default');
        INSERT INTO degraded_mode_state VALUES ('weather_unavailable', '2026-10-16T07:00:00+00:00', 'default');
        PRAGMA user_version = 32;
    """)
    raw.commit()
    raw.close()

    db = _db(tmp_path)
    try:
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 35
        info = list(db.conn.execute("PRAGMA table_info(degraded_mode_state)"))
        key = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
        assert key == ["athlete_id", "failure_type"]
        assert {row[1]: row[4] for row in info}["athlete_id"] is None, "athlete_id must have no DEFAULT"
        assert sorted(db.get_all_degraded_mode_states(athlete_id="owner")) == [
            ("garmin_data_stale", "2026-10-15T07:00:00+00:00"),
            ("weather_unavailable", "2026-10-16T07:00:00+00:00"),
        ]
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO degraded_mode_state (failure_type, degraded_since) VALUES ('x', 'y')"
            )
    finally:
        db.close()


@pytest.mark.unit
def test_operator_note_lands_on_the_named_athletes_decision(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        for athlete, session in (("owner", "EASY"), (A, "TEMPO")):  # A's decision is written last
            db.save_governance_decision({
                "athlete_profile_id": athlete, "date": TODAY,
                "session_planned": session, "session_post_governance": session,
            })

        assert db.annotate_governance_outcome(date=TODAY, note="owner felt sick") is True

        notes = dict(db.conn.execute(
            "SELECT athlete_id, outcome_notes FROM governance_outcomes WHERE date = ?", (TODAY,)
        ).fetchall())
        assert notes == {"owner": "owner felt sick", A: None}

        assert db.annotate_governance_outcome(date=TODAY, note="A skipped", athlete_id=A) is True
        assert db.annotate_governance_outcome(date=TODAY, note="nobody", athlete_id=B) is False
    finally:
        db.close()


@pytest.mark.unit
def test_manual_entry_reads_only_the_athletes_own_rows(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        db.conn.execute(
            "INSERT INTO daily_metrics (athlete_id, date, hrv_rmssd, resting_hr, data_source) "
            "VALUES ('owner', ?, 21.0, 70, 'manual_entry')",
            (TODAY,),
        )
        db.conn.commit()

        assert ManualEntryAdapter(db).get_hrv(TODAY) == 21.0
        assert ManualEntryAdapter(db, athlete_id="owner").get_rhr(TODAY) == 70.0
        athlete = ManualEntryAdapter(db, athlete_id=A)
        assert athlete.get_hrv(TODAY) is None
        assert athlete.get_rhr(TODAY) is None
    finally:
        db.close()


@pytest.mark.unit
def test_daily_coach_builds_its_tracker_for_its_own_athlete(tmp_path: Path) -> None:
    """The coach of athlete A keeps its degraded timers under A (ISO-2 wiring)."""
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

    db = _db(tmp_path)
    try:
        engines = EngineRegistry.from_db(db=db, athlete_id=A)
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
            athlete_id=A,
            engines=engines,
        )
        coach._degraded_tracker.update({"garmin_data_stale": True}, alert_fn=lambda _m: None)

        assert _rows(db) == [(A, "garmin_data_stale")]
    finally:
        db.close()


@pytest.mark.integration
def test_postgres_operator_note_lands_on_the_named_athletes_decision() -> None:
    """Same as ISO-3 on the PostgreSQL adapter (in-memory engine, as in test_persistence)."""
    from sqlalchemy import text

    from tests.titan.core.test_persistence import _build_test_engine

    engine, adapter = _build_test_engine()
    decision = {
        "date": TODAY, "session_planned": "EASY", "session_post_governance": "EASY",
        "locks_applied": [], "governance_clean": True, "phase": "P8", "vlg_color": "GREEN",
        "apl_priority_vector": [], "lock_thresholds_active": {}, "acwr": 1.0,
        "tsb_value": 0.0, "readiness_score": 70.0, "glycogen_debt": 0.0,
    }
    try:
        adapter.save_governance_decision(decision)
        adapter.save_governance_decision(decision)
        with engine.begin() as conn:  # the later row is athlete A's
            conn.execute(text(
                "UPDATE governance_outcomes SET athlete_id = :a "
                "WHERE id = (SELECT MAX(id) FROM governance_outcomes)"
            ), {"a": A})

        assert adapter.annotate_governance_outcome(date=TODAY, note="owner felt sick") is True
        assert adapter.annotate_governance_outcome(date=TODAY, note="nobody", athlete_id=B) is False

        with engine.connect() as conn:
            notes = dict(conn.execute(text(
                "SELECT athlete_id, outcome_notes FROM governance_outcomes WHERE date = :d"
            ), {"d": TODAY}).fetchall())
        assert notes == {"owner": "owner felt sick", A: None}
    finally:
        adapter.close()
