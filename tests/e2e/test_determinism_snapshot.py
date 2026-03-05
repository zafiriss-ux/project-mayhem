from __future__ import annotations

import hashlib
import json

from tests.e2e.conftest import (
    StubAPL,
    StubAutonomic,
    StubCS,
    StubFatigue,
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
)
from titan.core.database import DatabaseManager
from titan.orchestration import daily_coach
from titan.orchestration.daily_coach import DailyCoach


def _run_once(tmp_path, fixed_today: str, run_idx: int):
    events: list[dict] = []
    db = DatabaseManager(db_name=f"e2e_determinism_{run_idx}.db", db_dir=tmp_path)
    telegram = StubTelegram()

    coach = DailyCoach(
        garmin_sync=StubGarminSync(today=fixed_today),
        weather_api=StubWeather(),
        telegram_bot=telegram,
        hrv_engine=StubSimpleEngine(),
        tsb_engine=StubTSB(),
        readiness_engine=StubReadiness(),
        optimal_time_calc=StubOptimalTime(),
        nutrition_optimizer=StubNutrition(),
        weekly_planner=StubWeeklyPlanner(),
        db=db,
        autonomic_engine=StubAutonomic(),
        cs_tracker=StubCS(),
        glycogen_accum=StubGlycogen(),
        governance=StubGovernance(),
        fatigue_engine=StubFatigue(),
        apl=StubAPL(),
        volume_load_gauge=StubVLG(),
        outcome_tracker=StubOutcomeTracker(),
    )

    original_event = daily_coach._daily_coach_event
    daily_coach._daily_coach_event = (
        lambda action, **fields: events.append({"action": action, **fields})
    )

    try:
        assert coach.run_morning_routine() is True
        assert len(telegram.daily_messages) == 1
        payload = telegram.daily_messages[0]
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        session_type = payload["session_type"]
        event_names = tuple(event["action"] for event in events)

        return payload_hash, session_type, event_names
    finally:
        daily_coach._daily_coach_event = original_event
        db.close()


def test_determinism_snapshot_same_inputs_same_output(tmp_path):
    fixed_today = "2026-03-04"
    runs = [_run_once(tmp_path, fixed_today=fixed_today, run_idx=i) for i in range(10)]

    payload_hashes = {result[0] for result in runs}
    session_types = {result[1] for result in runs}
    event_name_sequences = {result[2] for result in runs}

    assert len(payload_hashes) == 1
    assert len(session_types) == 1
    assert len(event_name_sequences) == 1

    event_names = next(iter(event_name_sequences))
    assert "routine_started" in event_names
    assert "routine_completed" in event_names
