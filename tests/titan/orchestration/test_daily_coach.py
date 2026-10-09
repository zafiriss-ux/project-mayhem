import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from time import sleep
from types import SimpleNamespace

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration import daily_coach
from titan.orchestration.daily_coach import DailyCoach, DegradedModeTracker
from titan.orchestration.engine_registry import EngineRegistry


class DummyDB:
    def __init__(self) -> None:
        self._save_calls = 0

        class Cursor:
            def execute(self, *_args, **_kwargs):
                return None

            @staticmethod
            def fetchone():
                return None

        self.conn = SimpleNamespace(cursor=lambda: Cursor())

    @contextmanager
    def transaction(self):
        yield

    def save_session(self, **kwargs):
        self._save_calls += 1

    def save_daily_metric(self, **kwargs):
        return None

    def save_hrr(self, *args, **kwargs):
        return None

    def save_daily_metric_if_missing(self, *args, **kwargs):
        return None

    def update_glycogen_debt(self, *args, **kwargs):
        return None

    def get_baseline_rhr(self, days: int = 7, athlete_id: str = "owner"):
        return None

    def get_hrv_history(self, days: int = 14, athlete_id: str = "owner"):
        return []

    def get_weight_history(self, days: int = 30, athlete_id: str = "owner"):
        return []

    def get_training_load_history(self, days: int = 42, athlete_id: str = "owner"):
        return []

    def get_hrr_history(self, days: int = 28, athlete_id: str = "owner"):
        return []

    def get_cs_performances(self, limit: int = 10):
        return []

    def record_sync_outcome(self, **kwargs):
        self._last_sync_outcome = kwargs

    def get_last_sync_outcome(self, source: str):
        return None

    def is_athlete_cold_start(self, athlete_id: str) -> bool:
        return False

    def check_and_exit_cold_start(self, athlete_id: str) -> bool:
        return False

    def increment_cold_start_sessions(self, athlete_id: str) -> None:
        return None

    def get_athlete_threshold_offsets(self, athlete_id: str) -> list:
        return []


def _placeholder_engine_registry(**overrides):
    """Build an EngineRegistry of SimpleNamespace placeholders for init-only tests."""
    fields = ("tsb", "hrv", "readiness", "autonomic", "biomechanics",
              "durability", "fatigue", "lactate", "cs_tracker", "apl")
    kwargs = {name: SimpleNamespace() for name in fields}
    kwargs.update(overrides)
    return EngineRegistry(**kwargs)


class MinimalCoachFactory:
    @staticmethod
    def build(telegram_success: bool = True, sync_exception: Exception | None = None):
        coach = DailyCoach.__new__(DailyCoach)
        coach.db = DummyDB()
        coach.garmin = SimpleNamespace(
            sync_all=(lambda: (_ for _ in ()).throw(sync_exception))
            if sync_exception
            else lambda: {
                "activities": [
                    {"date": "2026-03-04", "session_type": "EASY", "distance_km": 5, "duration_sec": 1800},
                    {"date": "2026-03-04", "session_type": "EASY", "distance_km": 3, "duration_sec": 1200},
                ],
                "sleep": [{"restingHeartRate": 50, "sleepScores": {"overall": {"value": 80}}, "sleepTimeSeconds": 25200}],
                "hrv": [{"date": "2026-03-04", "rmssd": 45.0}],
                "hrr": [],
                "weight": [],
                "temperature_c": 20,
                "acwr": 1.0,
            }
        )
        coach.hrv = SimpleNamespace(
            hrv_log=[],
            add_hrv_measurement=lambda *a, **k: None,
            calculate_ln_rmssd_deviation=lambda **k: 0.0,
            get_hrv_summary=lambda: {"latest_hrv": 45.0, "baseline": 40.0, "trend": "steady", "std_dev": 1.0},
            check_baseline_drift=lambda **k: False,
        )
        coach.autonomic = SimpleNamespace(
            hrr_log=[],
            add_hrr=lambda *a, **k: None,
            calculate_afi=lambda **k: 0.2,
            apply_48h_buffer=lambda v: v,
            get_readiness_constraints=lambda *a, **k: {"afi_modifier": 0, "readiness_clamp": 100},
        )
        coach.tsb = SimpleNamespace(calculate_tsb=lambda: (0.0, "BALANCED"))
        coach.cs_tracker = SimpleNamespace(
            apply_thermal=lambda *_: 1.0,
            archetype="stable",
            cs_smoothed=3.5,
            confidence=1.0,
        )
        coach.glycogen = SimpleNamespace(
            daily_debt=0.0,
            status="OK",
            update=lambda **k: None,
            overnight_resynthesis=lambda **k: None,
            norwegian_protocol=lambda *_: {},
        )
        coach.readiness = SimpleNamespace(analyze_readiness=lambda **k: {"score": 60})
        coach.fatigue = SimpleNamespace(classify_fatigue=lambda **k: ("LOW", []))
        coach.weekly_planner = SimpleNamespace(get_today_session=lambda: {"session_type": "EASY", "volume_pct": 1.0, "duration_min": 45, "distance_km": 8})
        coach.vlg = SimpleNamespace(resolve=lambda **k: SimpleNamespace(color="GREEN"))
        coach.apl = SimpleNamespace(resolve=lambda **k: {"priority_vector": {}, "lock_thresholds": {}})
        coach.governance = SimpleNamespace(
            apply_constraints=lambda session_plan, context: {**session_plan, "governance_locks_applied": [], "governance_clean": True},
            get_governance_report=lambda **k: {},
        )
        coach.outcome_tracker = SimpleNamespace(record_decision=lambda **k: None)
        coach.athlete_max_hr = 0
        coach._degraded_tracker = DegradedModeTracker()
        coach.optimal_time = SimpleNamespace(calculate_optimal_time=lambda **k: {"recommended_time": "07:00", "dew_point": 12, "quality": "GOOD"})
        coach.nutrition = SimpleNamespace(
            analyze_weight_trend=lambda: {"current_weight": 70.0},
            add_weight_entry=lambda *a, **k: None,
            calculate_daily_nutrition=lambda **k: {"carbs_g": 250, "protein_g": 120},
        )
        coach.telegram = SimpleNamespace(
            send_daily_coaching=lambda payload: telegram_success,
            # Same signature as TitanTelegramBot.send_alert.
            send_alert=lambda title, message, level="warning": None,
        )
        return coach


@pytest.mark.unit
def test_run_morning_routine_happy_path_emits_step_success(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=True)
    assert coach.run_morning_routine() is True

    assert any(
        event["action"] == "step_event"
        and event["step_number"] == 12
        and event["outcome"] == "SUCCESS"
        and event["failure_class"] is None
        for event in events
    )


@pytest.mark.unit
def test_run_morning_routine_sync_failure_emits_data_missing(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(sync_exception=ValueError("missing_data"))

    with pytest.raises(ValueError):
        coach.run_morning_routine()

    assert any(
        event["action"] == "step_event"
        and event["step_number"] == 1
        and event["outcome"] == "FAILED"
        and event["failure_class"] == daily_coach.DATA_MISSING
        for event in events
    )


@pytest.mark.unit
def test_run_morning_routine_calls_apl_resolve_with_normalized_phase_and_cs_confidence():
    coach = MinimalCoachFactory.build(telegram_success=True)
    vlg_state = SimpleNamespace(color="GREEN")
    captured_kwargs = {}

    coach.weekly_planner = SimpleNamespace(
        get_today_session=lambda: {
            "session_type": "EASY",
            "volume_pct": 1.0,
            "duration_min": 45,
            "distance_km": 8,
            "phase": "build",
        }
    )
    coach.autonomic = SimpleNamespace(
        hrr_log=[],
        add_hrr=lambda *a, **k: None,
        calculate_afi=lambda **k: 0.2,
        apply_48h_buffer=lambda v: v,
        get_readiness_constraints=lambda *a, **k: {
            "afi_modifier": -2,
            "readiness_clamp": 93,
            "parasympathetic_guard": {"triggered": False},
        },
    )
    coach.cs_tracker = SimpleNamespace(
        apply_thermal=lambda *_: 1.0,
        archetype="stable",
        cs_smoothed=3.5,
        confidence=0.37,
    )
    coach.vlg = SimpleNamespace(resolve=lambda **_kwargs: vlg_state)

    def _capture_apl_call(**kwargs):
        captured_kwargs.update(kwargs)
        return {"priority_vector": {}, "lock_thresholds": {}}

    coach.apl = SimpleNamespace(resolve=_capture_apl_call)

    assert coach.run_morning_routine() is True
    assert captured_kwargs["vlg_state"] is vlg_state
    assert captured_kwargs["afi_constraints"] == {
        "afi_modifier": -2,
        "readiness_clamp": 93,
        "parasympathetic_guard": {"triggered": False},
    }
    assert captured_kwargs["phase"] == "BUILD"
    assert captured_kwargs["cs_confidence"] == pytest.approx(0.37)


@pytest.mark.unit
def test_run_morning_routine_defaults_apl_phase_and_cs_confidence_when_missing():
    coach = MinimalCoachFactory.build(telegram_success=True)
    captured_kwargs = {}

    coach.weekly_planner = SimpleNamespace(
        get_today_session=lambda: {
            "session_type": "EASY",
            "volume_pct": 1.0,
            "duration_min": 45,
            "distance_km": 8,
            "phase": None,
        }
    )
    coach.cs_tracker = SimpleNamespace(
        apply_thermal=lambda *_: 1.0,
        archetype="stable",
        cs_smoothed=3.5,
        confidence="0.42",
    )

    def _capture_apl_call(**kwargs):
        captured_kwargs.update(kwargs)
        return {"priority_vector": {}, "lock_thresholds": {}}

    coach.apl = SimpleNamespace(resolve=_capture_apl_call)

    assert coach.run_morning_routine() is True
    assert captured_kwargs["phase"] == "BASE"
    assert captured_kwargs["cs_confidence"] == pytest.approx(0.42)
    assert isinstance(captured_kwargs["cs_confidence"], float)


@pytest.mark.unit
def test_run_morning_routine_async_starts_thread_when_idle(monkeypatch):
    coach = DailyCoach.__new__(DailyCoach)
    coach.run_morning_routine = lambda: True
    coach._routine_mutex = threading.Lock()

    created_threads = []

    class FakeThread:
        def __init__(self, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False
            created_threads.append(self)

        def start(self):
            self.started = True

        def is_alive(self):
            return self.started

    monkeypatch.setattr(daily_coach.threading, "Thread", FakeThread)
    monkeypatch.setattr(daily_coach, "monotonic", lambda: 123.45)

    result = coach.run_morning_routine_async(trigger_source="scheduler")

    assert result is True
    assert len(created_threads) == 1
    assert created_threads[0].name == "DailyCoachRoutine"
    assert created_threads[0].daemon is True
    assert created_threads[0].started is True
    assert coach._routine_thread is created_threads[0]
    assert coach._routine_started_monotonic == 123.45


@pytest.mark.unit
def test_run_morning_routine_async_skips_when_thread_already_alive(monkeypatch):
    events = []
    coach = DailyCoach.__new__(DailyCoach)
    coach._routine_mutex = threading.Lock()
    # Simulate already-running: acquire the lock before calling async
    coach._routine_mutex.acquire()

    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))
    monkeypatch.setattr(
        daily_coach.threading,
        "Thread",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Thread should not be created on overlap")),
    )

    result = coach.run_morning_routine_async(trigger_source="telegram_poll")
    coach._routine_mutex.release()

    assert result is False
    assert len(events) == 1
    assert events[0]["action"] == "morning_routine_skipped"
    assert events[0]["reason"] == "already_running"
    assert events[0]["trigger_source"] == "telegram_poll"


@pytest.mark.unit
def test_daily_coach_no_overlap_guard():
    coach = DailyCoach.__new__(DailyCoach)
    coach._routine_mutex = threading.Lock()
    started = threading.Event()
    release = threading.Event()
    run_count = 0
    run_count_lock = threading.Lock()

    def _blocking_routine():
        nonlocal run_count
        with run_count_lock:
            run_count += 1
        started.set()
        release.wait(timeout=2)

    coach.run_morning_routine = _blocking_routine

    coach.run_morning_routine_async(trigger_source="test_first_call")
    assert started.wait(timeout=1)

    coach.run_morning_routine_async(trigger_source="test_second_call")
    sleep(0.05)

    with run_count_lock:
        assert run_count == 1

    release.set()
    coach._routine_thread.join(timeout=5)
    assert not coach._routine_thread.is_alive()


@pytest.mark.unit
def test_daily_coach_routine_thread_shutdown(tmp_path):
    coach = DailyCoach.__new__(DailyCoach)
    coach._routine_mutex = threading.Lock()
    db = DatabaseManager(db_name="daily_coach_thread_shutdown.db", db_dir=tmp_path)
    programming_errors: list[sqlite3.ProgrammingError] = []

    def _routine_with_db_touch():
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            db.save_daily_metric(date=today, hrv=45.0, rhr=52, sleep_hours=7.0)
            db.get_training_load_history(days=7)
        except sqlite3.ProgrammingError as exc:
            programming_errors.append(exc)
            raise

    coach.run_morning_routine = _routine_with_db_touch

    try:
        coach.run_morning_routine_async(trigger_source="thread_shutdown_test")
        assert coach._routine_thread is not None
        coach._routine_thread.join(timeout=5)
        assert not coach._routine_thread.is_alive()
        assert not programming_errors
    finally:
        db.close()


def _garmin_payload_for_day(day: str = "2026-03-04") -> dict:
    return {
        "activities": [
            {
                "activity_id": "garmin-activity-1",
                "date": day,
                "session_type": "EASY",
                "distance_km": 5,
                "duration_sec": 1800,
                "rpe": 4,
                "name": "AM",
            },
            {
                "activity_id": "garmin-activity-2",
                "date": day,
                "session_type": "TEMPO",
                "distance_km": 8,
                "duration_sec": 2400,
                "rpe": 7,
                "name": "PM",
            },
        ],
        "sleep": [{"restingHeartRate": 50, "sleepScores": {"overall": {"value": 80}}, "sleepTimeSeconds": 25200}],
        "hrv": [{"date": day, "rmssd": 45.0}],
        "weight": [{"date": day, "weight_kg": 70.5}],
    }


def _build_atomic_persist_coach(db: DatabaseManager) -> DailyCoach:
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = db
    return coach


def _count_rows(db: DatabaseManager, table: str, day: str) -> int:
    cursor = db.conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE date = ?", (day,))
    return int(cursor.fetchone()[0])


@pytest.mark.unit
def test_persist_garmin_data_success_commits_activities_and_metrics_atomically(tmp_path):
    db = DatabaseManager(db_name="atomic_success.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-04"

    try:
        rhr, sleep_score, sleep_hours = coach._persist_garmin_data(_garmin_payload_for_day(day), day)

        assert (rhr, sleep_score, sleep_hours) == (50, 80, 7.0)
        assert _count_rows(db, "training_log", day) == 2
        assert _count_rows(db, "daily_metrics", day) == 1
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_invalid_physiological_values_are_surfaced_and_sanitized(
    tmp_path,
    monkeypatch,
):
    events = []
    monkeypatch.setattr(
        daily_coach,
        "_daily_coach_event",
        lambda action, **fields: events.append({"action": action, **fields}),
    )

    db = DatabaseManager(db_name="atomic_invalid_physio.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-04"
    payload = _garmin_payload_for_day(day)
    payload["sleep"] = [{
        "restingHeartRate": 300,
        "sleepScores": {"overall": {"value": 80}},
        "sleepTimeSeconds": 200000,
    }]
    payload["hrv"] = [{"date": day, "rmssd": 0.0}]
    payload["weight"] = [{"date": day, "weight_kg": 900.0}]

    try:
        rhr, sleep_score, sleep_hours = coach._persist_garmin_data(payload, day)

        assert rhr == 0
        assert sleep_score == 80
        assert sleep_hours == 0.0

        row = db.conn.execute(
            """SELECT resting_hr, hrv_rmssd, weight_kg, sleep_hours
               FROM daily_metrics WHERE date = ?""",
            (day,),
        ).fetchone()
        assert row == (None, None, None, None)

        validation_events = [
            e for e in events if e["action"] == "physiological_input_validation_failed"
        ]
        assert validation_events
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_failure_mid_loop_rolls_back_entire_day(tmp_path):
    from titan.orchestration.daily_coach import PersistenceFailure

    class MidLoopFailDB(DatabaseManager):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._session_calls = 0

        def save_session(self, **kwargs):
            self._session_calls += 1
            if self._session_calls == 2:
                raise RuntimeError("mid_loop_failure")
            return super().save_session(**kwargs)

    db = MidLoopFailDB(db_name="atomic_midloop_fail.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-04"

    try:
        with pytest.raises(PersistenceFailure):
            coach._persist_garmin_data(_garmin_payload_for_day(day), day)

        assert _count_rows(db, "training_log", day) == 0
        assert _count_rows(db, "daily_metrics", day) == 0
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_failure_during_daily_metric_rolls_back_activities(tmp_path):
    from titan.orchestration.daily_coach import PersistenceFailure

    class MetricFailDB(DatabaseManager):
        def save_daily_metric(self, **kwargs):
            raise RuntimeError("metric_failure")

    db = MetricFailDB(db_name="atomic_metric_fail.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-04"

    try:
        with pytest.raises(PersistenceFailure):
            coach._persist_garmin_data(_garmin_payload_for_day(day), day)

        assert _count_rows(db, "training_log", day) == 0
        assert _count_rows(db, "daily_metrics", day) == 0
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_duplicate_activity_ids_in_same_payload_are_rejected(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(
        daily_coach,
        "_daily_coach_event",
        lambda action, **fields: events.append({"action": action, **fields}),
    )

    db = DatabaseManager(db_name="garmin_duplicate_payload.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-04"

    try:
        payload = _garmin_payload_for_day(day)
        payload["activities"][1]["activity_id"] = payload["activities"][0]["activity_id"]

        coach._persist_garmin_data(payload, day)

        assert _count_rows(db, "training_log", day) == 1
        assert _count_rows(db, "daily_metrics", day) == 1
        assert any(
            event["action"] == "activity_persist"
            and event.get("outcome") == "ACTIVITY_SANITY_REJECTED"
            for event in events
        )
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_duplicate_sync_is_idempotent(tmp_path):
    db = DatabaseManager(db_name="garmin_idempotent_sync.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-04"

    try:
        payload = _garmin_payload_for_day(day)

        coach._persist_garmin_data(payload, day)
        rows_after_first_sync = _count_rows(db, "training_log", day)
        tsb_after_first_sync = db.get_ctl_atl_tsb()

        coach._persist_garmin_data(payload, day)
        rows_after_second_sync = _count_rows(db, "training_log", day)
        tsb_after_second_sync = db.get_ctl_atl_tsb()

        assert rows_after_first_sync == rows_after_second_sync
        assert tsb_after_first_sync == tsb_after_second_sync
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_f29_flattened_sleep_keys_are_parsed(tmp_path):
    """F-29: _persist_garmin_data must read sync_sleep() flattened keys
    (sleep_score, total_sleep_hours) and return correct values."""
    db = DatabaseManager(db_name="f29_flattened_sleep.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-10"

    # Payload using the flattened keys returned by sync_sleep()
    payload = _garmin_payload_for_day(day)
    payload["sleep"] = [{"sleep_score": 85, "total_sleep_hours": 7.5}]

    try:
        rhr, sleep_score, sleep_hours = coach._persist_garmin_data(payload, day)

        assert sleep_score == 85
        assert sleep_hours == 7.5
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_sync_sleep_output_sleep_score_extracted_correctly(tmp_path):
    """T5-60: _persist_garmin_data must extract sleep_score from the exact shape
    that sync_sleep() produces — not fall back to the optimistic 75 default."""
    db = DatabaseManager(db_name="t5_60_sleep_score.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-20"

    # Exact output shape returned by sync_sleep() — no raw Garmin keys present.
    payload = _garmin_payload_for_day(day)
    payload["sleep"] = [
        {
            "date": day,
            "total_sleep_hours": 7.2,
            "deep_sleep_hours": 1.4,
            "rem_sleep_hours": 1.9,
            "sleep_score": 78,
        }
    ]

    try:
        rhr, sleep_score, sleep_hours = coach._persist_garmin_data(payload, day)

        # sleep_score must reflect the sync_sleep() value, NOT the 75 default.
        assert sleep_score == 78
        assert sleep_hours == pytest.approx(7.2, abs=0.01)
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_uses_last_nights_sleep_and_resting_hr(tmp_path):
    """sync_sleep() returns 14 nights newest first; only today's entry describes today.

    The loop used to keep the last entry it saw, i.e. the oldest night in the window.
    """
    db = DatabaseManager(db_name="today_sleep_entry.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-21"
    payload = _garmin_payload_for_day(day)
    payload["sleep"] = [
        {"date": day, "total_sleep_hours": 6.5, "sleep_score": 64, "resting_hr": 47},
        {"date": "2026-03-20", "total_sleep_hours": 8.0, "sleep_score": 88, "resting_hr": None},
        {"date": "2026-03-08", "total_sleep_hours": 9.0, "sleep_score": 91, "resting_hr": 60},
    ]

    try:
        rhr, sleep_score, sleep_hours = coach._persist_garmin_data(payload, day)

        assert (rhr, sleep_score, sleep_hours) == (47, 64, 6.5)
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_sync_sleep_output_rhr_is_absent(tmp_path):
    """T5-60: sync_sleep() does not include a restingHeartRate key.
    _persist_garmin_data must return today_rhr == 0 (→ None after validation)
    when the sleep entry comes from sync_sleep(), not a non-zero phantom value."""
    db = DatabaseManager(db_name="t5_60_rhr_absent.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-21"

    # Exact sync_sleep() output shape — deliberately omits restingHeartRate / rhr.
    payload = _garmin_payload_for_day(day)
    payload["sleep"] = [
        {
            "date": day,
            "total_sleep_hours": 7.0,
            "deep_sleep_hours": 1.2,
            "rem_sleep_hours": 1.7,
            "sleep_score": 82,
        }
    ]
    # Remove HRV so that RHR cannot come from another source in this test.
    payload["hrv"] = []

    try:
        rhr, sleep_score, sleep_hours = coach._persist_garmin_data(payload, day)

        # RHR must be 0 (→ None downstream) because sync_sleep() has no RHR key.
        assert rhr == 0
        assert sleep_score == 82
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_missing_sleep_data_defaults_are_conservative(tmp_path):
    """T5-60 regression: when sleep data is entirely absent the default
    sleep_score must be conservative (< 70, i.e. negative sleep_delta),
    not the former optimistic 75 default."""
    db = DatabaseManager(db_name="t5_60_conservative_default.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-22"

    payload = _garmin_payload_for_day(day)
    payload["sleep"] = []   # No sleep data at all

    try:
        _rhr, sleep_score, _sleep_hours = coach._persist_garmin_data(payload, day)

        # Conservative: score must be below 70 so sleep_delta is negative.
        assert sleep_score < 70, (
            f"Default sleep_score {sleep_score} is not conservative "
            f"(must be < 70 to produce negative sleep_delta)"
        )
        # Sanity: definitely not the old optimistic 75 or a perfect 100.
        assert sleep_score != 75
        assert sleep_score != 100
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_f32_multi_day_hrv_all_persisted(tmp_path):
    """F-32: _persist_garmin_data must persist HRV for every date returned by
    sync_hrv(), not only today."""
    db = DatabaseManager(db_name="f32_multi_day_hrv.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    today = "2026-03-10"
    yesterday = "2026-03-09"
    two_days_ago = "2026-03-08"

    payload = _garmin_payload_for_day(today)
    payload["hrv"] = [
        {"date": today, "rmssd": 45.0},
        {"date": yesterday, "rmssd": 42.0},
        {"date": two_days_ago, "rmssd": 38.0},
    ]

    try:
        coach._persist_garmin_data(payload, today)

        # Today's HRV is stored via the main save_daily_metric call
        assert _count_rows(db, "daily_metrics", today) == 1
        # Historical HRV entries must each have a row too
        assert _count_rows(db, "daily_metrics", yesterday) == 1
        assert _count_rows(db, "daily_metrics", two_days_ago) == 1

        row_today = db.conn.execute(
            "SELECT hrv_rmssd FROM daily_metrics WHERE date = ?", (today,)
        ).fetchone()
        row_yesterday = db.conn.execute(
            "SELECT hrv_rmssd FROM daily_metrics WHERE date = ?", (yesterday,)
        ).fetchone()
        row_two_days_ago = db.conn.execute(
            "SELECT hrv_rmssd FROM daily_metrics WHERE date = ?", (two_days_ago,)
        ).fetchone()

        assert row_today[0] == pytest.approx(45.0, abs=0.1)
        assert row_yesterday[0] == pytest.approx(42.0, abs=0.1)
        assert row_two_days_ago[0] == pytest.approx(38.0, abs=0.1)
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_f32_seven_day_hrv_all_persisted(tmp_path):
    """F-32 / T5-61: 7-day HRV sync result must produce exactly 7 rows in daily_metrics."""
    db = DatabaseManager(db_name="f32_seven_day_hrv.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    today = "2026-03-10"
    dates = [
        "2026-03-10",
        "2026-03-09",
        "2026-03-08",
        "2026-03-07",
        "2026-03-06",
        "2026-03-05",
        "2026-03-04",
    ]

    payload = _garmin_payload_for_day(today)
    payload["hrv"] = [{"date": d, "rmssd": 40.0 + i} for i, d in enumerate(dates)]

    try:
        coach._persist_garmin_data(payload, today)

        for d in dates:
            assert _count_rows(db, "daily_metrics", d) == 1, f"Missing row for {d}"
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_f32_historical_entry_not_overwritten(tmp_path):
    """T5-61: Historical HRV entries use INSERT OR IGNORE — manually entered data must
    not be overwritten by a Garmin sync backfill."""
    db = DatabaseManager(db_name="f32_no_overwrite.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    today = "2026-03-10"
    yesterday = "2026-03-09"

    # Manually entered HRV for yesterday (simulates user check-in)
    db.save_daily_metric(date=yesterday, hrv=99.0, rhr=48)

    payload = _garmin_payload_for_day(today)
    payload["hrv"] = [
        {"date": today, "rmssd": 45.0},
        {"date": yesterday, "rmssd": 55.0},  # Garmin value must NOT overwrite manual 99.0
    ]

    try:
        coach._persist_garmin_data(payload, today)

        row = db.conn.execute(
            "SELECT hrv_rmssd, resting_hr FROM daily_metrics WHERE date = ?", (yesterday,)
        ).fetchone()
        assert row is not None
        # hrv_rmssd must remain 99.0 (manual entry), not 55.0 (Garmin backfill)
        assert row[0] == pytest.approx(99.0, abs=0.1), (
            f"Historical HRV was overwritten: expected 99.0, got {row[0]}"
        )
        # Other fields must also survive intact
        assert row[1] == 48
    finally:
        db.close()


@pytest.mark.unit
def test_persist_garmin_data_f32_today_entry_persisted_normally(tmp_path):
    """T5-61 regression: today's entry must still be persisted via INSERT OR REPLACE
    (today uses save_daily_metric, not save_daily_metric_if_missing)."""
    db = DatabaseManager(db_name="f32_today_regression.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    today = "2026-03-10"

    payload = _garmin_payload_for_day(today)
    payload["hrv"] = [{"date": today, "rmssd": 52.0}]

    try:
        coach._persist_garmin_data(payload, today)

        row = db.conn.execute(
            "SELECT hrv_rmssd FROM daily_metrics WHERE date = ?", (today,)
        ).fetchone()
        assert row is not None
        assert row[0] == pytest.approx(52.0, abs=0.1)
    finally:
        db.close()


@pytest.mark.unit
def test_get_baseline_rhr_happy_path_returns_average():
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = SimpleNamespace(get_baseline_rhr=lambda days=7, athlete_id="owner": 51.3)

    assert coach._get_baseline_rhr(days=7) == 51.3


@pytest.mark.unit
def test_get_baseline_rhr_error_emits_unavailable_and_returns_none(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = DailyCoach.__new__(DailyCoach)

    def _raise_value_error(days=7, athlete_id="owner"):
        raise ValueError("broken_row")

    coach.db = SimpleNamespace(get_baseline_rhr=_raise_value_error)

    assert coach._get_baseline_rhr(days=7) is None
    assert events == [
        {
            "action": "baseline_rhr_unavailable",
            "error_class": "ValueError",
            "detail": "broken_row",
        }
    ]


@pytest.mark.unit
def test_run_morning_routine_uses_degraded_mode_when_baseline_missing(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=True)
    baseline_args: dict[str, float] = {}
    governance_baseline = {}

    def _readiness_spy(**kwargs):
        baseline_args["baseline_rhr"] = kwargs["baseline_rhr"]
        baseline_args["today_rhr"] = kwargs["today_rhr"]
        return {"score": 60}

    def _governance_spy(session_plan, context):
        governance_baseline["baseline_rhr"] = context["baseline_rhr"]
        return {**session_plan, "governance_locks_applied": [], "governance_clean": True}

    coach.readiness = SimpleNamespace(analyze_readiness=_readiness_spy)
    coach.governance = SimpleNamespace(apply_constraints=_governance_spy, get_governance_report=lambda **_k: {})
    coach._get_baseline_rhr = lambda days=7: None

    assert coach.run_morning_routine() is True
    assert baseline_args["baseline_rhr"] == baseline_args["today_rhr"]
    assert governance_baseline["baseline_rhr"] == baseline_args["today_rhr"]
    assert any(event["action"] == "baseline_rhr_degraded_mode" for event in events)


@pytest.mark.unit
def test_run_morning_routine_h3_comparison_uses_valid_baseline(monkeypatch):
    coach = MinimalCoachFactory.build(telegram_success=True)
    baseline_args: dict[str, float] = {}
    governance_baseline = {}

    def _readiness_spy(**kwargs):
        baseline_args["baseline_rhr"] = kwargs["baseline_rhr"]
        baseline_args["today_rhr"] = kwargs["today_rhr"]
        return {"score": 60}

    def _governance_spy(session_plan, context):
        governance_baseline["baseline_rhr"] = context["baseline_rhr"]
        return {**session_plan, "governance_locks_applied": [], "governance_clean": True}

    coach.readiness = SimpleNamespace(analyze_readiness=_readiness_spy)
    coach.governance = SimpleNamespace(apply_constraints=_governance_spy, get_governance_report=lambda **_k: {})
    coach._get_baseline_rhr = lambda days=7: 47.2

    assert coach.run_morning_routine() is True
    assert baseline_args["baseline_rhr"] == 47.2
    assert governance_baseline["baseline_rhr"] == 47.2


@pytest.mark.unit
def test_build_daily_coach_context_supports_dict_access_and_serialization():
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = object()
    coach.cs_tracker = object()

    context = coach._build_daily_coach_context(
        afi_constraints={"afi_modifier": -5},
        intensity_gate={"color": "YELLOW"},
        readiness_score=67.0,
        glycogen_debt=23.5,
        fatigue_level="MODERATE",
        acwr=1.12,
        days_since_last_vo2=3,
        fueling_confirmed=True,
        planned_duration_min=70,
        today_hrv=42.1,
        baseline_hrv=48.7,
        hrv_std_dev=4.2,
        today_rhr=52,
        baseline_rhr=50.0,
        sleep_score=76,
        subjective_fatigue_score=4,
        tsb_value=-8.0,
        injury_flag=False,
        priority_vector={"recovery": 1},
        lock_thresholds={"acwr": 1.25},
    )

    assert context["intensity_gate_result"]["color"] == "YELLOW"
    assert context["priority_vector"] == {"recovery": 1}
    assert set(context) == {
        "db",
        "cs_tracker",
        "afi_constraints",
        "intensity_gate_result",
        "readiness_score",
        "glycogen_debt",
        "fatigue_level",
        "acwr",
        "days_since_last_vo2",
        "fueling_confirmed",
        "planned_duration_min",
        "today_hrv",
        "baseline_hrv",
        "hrv_std_dev",
        "today_rhr",
        "baseline_rhr",
        "sleep_score",
        "subjective_fatigue_score",
        "tsb_value",
        "injury_flag",
        "priority_vector",
        "lock_thresholds",
    }



@pytest.mark.unit
def test_build_daily_coach_context_serializes_like_dict_payload():
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = object()
    coach.cs_tracker = object()

    context = coach._build_daily_coach_context(
        afi_constraints={"afi_modifier": 0},
        intensity_gate={"color": "GREEN"},
        readiness_score=80.0,
        glycogen_debt=10.0,
        fatigue_level="LOW",
        acwr=1.0,
        days_since_last_vo2=2,
        fueling_confirmed=False,
        planned_duration_min=45,
        today_hrv=50.0,
        baseline_hrv=48.0,
        hrv_std_dev=3.0,
        today_rhr=49,
        baseline_rhr=50.0,
        sleep_score=82,
        subjective_fatigue_score=2,
        tsb_value=1.0,
        injury_flag=False,
        priority_vector={},
        lock_thresholds={},
    )

    import json

    serializable_context = {k: v for k, v in context.items() if k not in {"db", "cs_tracker"}}
    serialized = json.loads(json.dumps(serializable_context))
    assert serialized["days_since_last_vo2"] == 2
    assert serialized["planned_duration_min"] == 45


@pytest.mark.unit
def test_build_daily_coach_context_preserves_nullable_days_since_last_vo2():
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = object()
    coach.cs_tracker = object()

    context = coach._build_daily_coach_context(
        afi_constraints={"afi_modifier": 0},
        intensity_gate={"color": "GREEN"},
        readiness_score=80.0,
        glycogen_debt=10.0,
        fatigue_level="LOW",
        acwr=1.0,
        days_since_last_vo2=None,
        fueling_confirmed=False,
        planned_duration_min=45,
        today_hrv=50.0,
        baseline_hrv=48.0,
        hrv_std_dev=3.0,
        today_rhr=49,
        baseline_rhr=50.0,
        sleep_score=82,
        subjective_fatigue_score=2,
        tsb_value=1.0,
        injury_flag=False,
        priority_vector={},
        lock_thresholds={},
    )

    assert context["days_since_last_vo2"] is None


@pytest.mark.unit
def test_run_morning_routine_omits_weather_recommendation_when_synthetic():
    captured_payload = {}
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.optimal_time = SimpleNamespace(
        calculate_optimal_time=lambda **k: {
            "recommended_time": "07:00",
            "dew_point": 12,
            "quality": "GOOD",
            "weather_data_quality": "synthetic",
        }
    )
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: captured_payload.update(payload) or True
    )

    assert coach.run_morning_routine() is True
    assert captured_payload["optimal_time"] == "N/A"
    assert captured_payload["dew_point"] == "N/A"
    assert captured_payload["special_note"] == "⚠️ Weather data unavailable — optimal time window omitted"


@pytest.mark.unit
def test_run_morning_routine_keeps_weather_recommendation_when_live():
    captured_payload = {}
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.optimal_time = SimpleNamespace(
        calculate_optimal_time=lambda **k: {
            "recommended_time": "06:30",
            "dew_point": 11,
            "quality": "🟩 EXCELLENT",
            "weather_data_quality": "live",
        }
    )
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: captured_payload.update(payload) or True
    )

    assert coach.run_morning_routine() is True
    assert captured_payload["optimal_time"] == "06:30"
    assert captured_payload["dew_point"] == 11
    assert "special_note" not in captured_payload




@pytest.mark.unit
def test_run_morning_routine_fresh_garmin_data_keeps_planned_session_type():
    captured = {}
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.db.get_last_sync_outcome = lambda source: {
        "last_success_ts": datetime.now(),
        "last_error_class": None,
    }

    def _governance_spy(session_plan, context):
        captured["session_type_before_governance"] = session_plan["session_type"]
        captured["garmin_data_stale"] = context.get("garmin_data_stale")
        return {**session_plan, "governance_locks_applied": [], "governance_clean": True}

    coach.governance = SimpleNamespace(apply_constraints=_governance_spy, get_governance_report=lambda **_k: {})

    assert coach.run_morning_routine() is True
    assert captured["session_type_before_governance"] == "EASY"
    assert captured["garmin_data_stale"] is False


@pytest.mark.unit
def test_run_morning_routine_stale_garmin_data_forces_easy_and_sets_context_flag(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    captured = {}
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.weekly_planner = SimpleNamespace(
        get_today_session=lambda: {"session_type": "INTERVAL", "volume_pct": 1.0, "duration_min": 75, "distance_km": 12}
    )
    coach.db.get_last_sync_outcome = lambda source: {
        "last_success_ts": datetime.now() - timedelta(hours=27),
        "last_error_class": "GARMIN_TIMEOUT",
    }

    def _governance_spy(session_plan, context):
        captured["session_type_before_governance"] = session_plan["session_type"]
        captured["duration_before_governance"] = session_plan["duration_min"]
        captured["garmin_data_stale"] = context.get("garmin_data_stale")
        return {**session_plan, "governance_locks_applied": [], "governance_clean": True}

    coach.governance = SimpleNamespace(apply_constraints=_governance_spy, get_governance_report=lambda **_k: {})

    assert coach.run_morning_routine() is True
    assert captured["session_type_before_governance"] == "EASY"
    assert captured["duration_before_governance"] == 45
    assert captured["garmin_data_stale"] is True
    assert any(event["action"] == "garmin_data_stale" for event in events)

@pytest.mark.unit
def test_run_morning_routine_boundary_empty_inputs_no_crash():
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.garmin = SimpleNamespace(
        sync_all=lambda: {
            "activities": [],
            "sleep": [],
            "hrv": [],
            "hrr": [],
            "weight": [],
            "acwr": 0.0,
        }
    )

    assert coach.run_morning_routine() is True


@pytest.mark.unit
def test_run_morning_routine_partial_sleep_payload_uses_safe_defaults():
    payload = {}
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.garmin = SimpleNamespace(
        sync_all=lambda: {
            "activities": [],
            "sleep": [
                {
                    "restingHeartRate": None,
                    "sleepScores": {"overall": "bad_value"},
                    "sleepTimeSeconds": None,
                }
            ],
            "hrv": [],
            "hrr": [],
            "weight": [],
            "acwr": 1.0,
        }
    )
    coach.telegram = SimpleNamespace(send_daily_coaching=lambda data: payload.update(data) or True)

    assert coach.run_morning_routine() is True
    assert payload["sleep_quality"] == 50  # conservative default (< 70 → negative sleep_delta)
    assert payload["sleep_hours"] == 7.5


@pytest.mark.unit
def test_run_morning_routine_same_inputs_produce_deterministic_payloads():
    payloads = []

    def _capture(payload):
        payloads.append(payload.copy())
        return True

    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.telegram = SimpleNamespace(send_daily_coaching=_capture)

    assert coach.run_morning_routine() is True
    assert coach.run_morning_routine() is True
    assert payloads[0] == payloads[1]


@pytest.mark.unit
def test_run_morning_routine_weekly_planner_exception_fails_closed_with_engine_failure_event(monkeypatch):
    """INV-12: a step-8 engine exception is recorded as FAILED/ENGINE_ERROR, then
    caught by coaching_pipeline's boundary guard — run_morning_routine returns
    False (no prescription) instead of letting the exception bubble up."""
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.weekly_planner = SimpleNamespace(
        get_today_session=lambda: (_ for _ in ()).throw(RuntimeError("planner_offline"))
    )

    assert coach.run_morning_routine() is False

    assert any(
        event["action"] == "step_event"
        and event["step_number"] == 8
        and event["outcome"] == "FAILED"
        and event["failure_class"] == daily_coach.ENGINE_ERROR
        for event in events
    )


@pytest.mark.unit
def test_run_morning_routine_telegram_falsey_result_returns_false_and_emits_delivery_alert(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=False)

    assert coach.run_morning_routine() is False
    assert any(
        event["action"] == "step_event"
        and event["step_number"] == 12
        and event["outcome"] == "FAILED"
        and event["failure_class"] == daily_coach.DELIVERY_ERROR
        for event in events
    )
    assert any(
        event["action"] == "slo_alert" and event["slo_key"] == "telegram_delivery_failed" for event in events
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("step_number", "error", "expected"),
    [
        (2, RuntimeError("persist"), daily_coach.PERSIST_ERROR),
        (12, RuntimeError("delivery"), daily_coach.DELIVERY_ERROR),
        (8, ValueError("bad_data"), daily_coach.DATA_MISSING),
        (8, RuntimeError("engine"), daily_coach.ENGINE_ERROR),
    ],
)
def test_failure_class_for_step_maps_error_taxonomy(step_number, error, expected):
    assert daily_coach._failure_class_for_step(step_number, error) == expected


@pytest.mark.unit
def test_ensure_vo2_eligibility_contract_normalizes_non_list_fields():
    session_plan = {
        "vo2_eligibility": {
            "failed_conditions": "readiness_low",
            "detailed_failed_conditions": {"code": "x"},
        }
    }

    DailyCoach._ensure_vo2_eligibility_contract(session_plan)

    assert session_plan["vo2_eligibility"]["failed_conditions"] == ["readiness_low"]
    assert session_plan["vo2_eligibility"]["detailed_failed_conditions"] == []


@pytest.mark.unit
def test_get_recent_trimp_prefers_trimp_and_falls_back_to_training_load():
    coach = DailyCoach.__new__(DailyCoach)

    total = coach._get_recent_trimp(
        [
            {"trimp": 75.5},
            {"trimp": 0, "training_load": 100},
        ]
    )

    assert total == 135.5


@pytest.mark.unit
def test_feed_load_engines_rehydrates_tsb_in_oldest_first_order(monkeypatch):
    events = []
    added = []
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = SimpleNamespace(
        get_training_load_history=lambda days=42, athlete_id="owner": [
            ("2026-03-03", 70.0),
            ("2026-03-04", 80.0),
        ]
    )
    coach.tsb = SimpleNamespace(
        daily_loads=[("old", 1.0)],
        add_daily_load=lambda date_str, load: added.append((date_str, load)),
    )
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append((action, fields)))

    coach._feed_load_engines([])

    assert coach.tsb.daily_loads == []
    assert added == [("2026-03-03", 70.0), ("2026-03-04", 80.0)]
    assert any(action == "load_engines_refreshed" and fields["sessions"] == 2 for action, fields in events)


@pytest.mark.unit
def test_run_morning_routine_handles_hrr_locks_weight_and_missing_nutrition(monkeypatch):
    events = []
    payload = {}
    hrr_calls = []
    save_hrr_calls = []
    glycogen_updates = []
    coach = MinimalCoachFactory.build(telegram_success=True)
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach.garmin = SimpleNamespace(
        sync_all=lambda: {
            "activities": [{"date": "2026-03-04", "session_type": "EASY", "distance_km": 5, "duration_sec": 1800, "trimp": 42}],
            "sleep": [None, {"restingHeartRate": 52, "sleepScores": 81, "sleepTimeSeconds": 25200}],
            "hrv": [{"date": "2026-03-04", "rmssd": 45.0}],
            "hrr": [{"date": "2026-03-04", "hrr_60": 25, "hrr_120": 42}],
            "weight": [{"date": "2026-03-04", "weight_kg": 73.4}],
            "acwr": 1.0,
        }
    )
    coach.autonomic = SimpleNamespace(
        hrr_log=[],
        add_hrr=lambda date, hrr_60, hrr_120: hrr_calls.append((date, hrr_60, hrr_120)),
        calculate_afi=lambda **k: 0.2,
        apply_48h_buffer=lambda v: v,
        get_readiness_constraints=lambda *a, **k: {"afi_modifier": 0, "readiness_clamp": 100},
    )
    coach.db.save_hrr = lambda date, hrr_60, hrr_120, **kw: save_hrr_calls.append((date, hrr_60, hrr_120))
    coach.governance = SimpleNamespace(
        apply_constraints=lambda session_plan, context: {
            **session_plan,
            "governance_locks_applied": ["LOCK_HYDRATION"],
            "governance_clean": False,
        },
        get_governance_report=lambda **k: {},
    )
    coach.glycogen = SimpleNamespace(
        daily_debt=5.0,
        status="OK",
        update=lambda **kwargs: glycogen_updates.append(kwargs),
        overnight_resynthesis=lambda **k: None,
        norwegian_protocol=lambda *_: {},
    )
    coach.nutrition = SimpleNamespace(
        analyze_weight_trend=lambda: {"current_weight": 70.0},
        add_weight_entry=lambda *a, **k: None,
        calculate_daily_nutrition=lambda **k: {},
    )
    coach.telegram = SimpleNamespace(send_daily_coaching=lambda data: payload.update(data) or True)

    assert coach.run_morning_routine() is True
    assert hrr_calls == [("2026-03-04", 25, 42)]
    assert save_hrr_calls == [("2026-03-04", 25, 42)]
    assert len(glycogen_updates) == 1
    assert payload["nutrition_plan"] == "?g carbs, ?g protein"
    assert any(event["action"] == "governance_locks_applied" for event in events)
    assert any(event["action"] == "slo_alert" and event["slo_key"] == "nutrition_plan_missing" for event in events)


@pytest.mark.unit
def test_run_morning_routine_telegram_exception_raises_delivery_error_event(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda _payload: (_ for _ in ()).throw(RuntimeError("telegram_offline"))
    )

    with pytest.raises(RuntimeError, match="telegram_offline"):
        coach.run_morning_routine()

    assert any(
        event["action"] == "step_event"
        and event["step_number"] == 12
        and event["outcome"] == "FAILED"
        and event["failure_class"] == daily_coach.DELIVERY_ERROR
        for event in events
    )


def _make_hydration_coach(db):
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = db
    coach._routine_mutex = threading.Lock()
    coach.hrv = SimpleNamespace(hrv_log=[], add_hrv_measurement=lambda *_: None, check_baseline_drift=lambda **k: False)
    coach.nutrition = SimpleNamespace(add_weight_entry=lambda *_: None)
    coach.tsb = SimpleNamespace(daily_loads=[], add_daily_load=lambda *_: None)
    coach.autonomic = SimpleNamespace(add_hrr=lambda *_: None)
    coach.cs_tracker = SimpleNamespace(confidence=1.0, archetype="stable", update=lambda *_: None)
    return coach


class _HydrationDB:
    def __init__(self, *, hrv=None, weight=None, load=None, hrr=None, cs=None):
        self._hrv = hrv if hrv is not None else []
        self._weight = weight if weight is not None else []
        self._load = load if load is not None else []
        self._hrr = hrr if hrr is not None else []
        self._cs = cs if cs is not None else []

    def get_hrv_history(self, days=14, athlete_id="owner"):
        return self._hrv

    def get_weight_history(self, days=30, athlete_id="owner"):
        return self._weight

    def get_training_load_history(self, days=42, athlete_id="owner"):
        return self._load

    def get_hrr_history(self, days=28, athlete_id="owner"):
        return self._hrr

    def get_cs_performances(self, limit=10):
        return self._cs


class _HydrationFailureDB:
    def __getattr__(self, _name):
        raise RuntimeError("hydrate_failure")


@pytest.mark.unit
def test_hydrate_engines_from_db_emits_failure_events_for_each_branch(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = _make_hydration_coach(_HydrationFailureDB())

    confidence = coach._hydrate_engines_from_db()

    assert confidence == {"hrv": False, "weight": False, "load": False, "hrr": False, "cs": False, "freshness": True}
    for action in {
        "hrv_hydration_failed",
        "weight_hydration_failed",
        "tsb_hydration_failed",
        "hrr_hydration_failed",
        "cs_hydration_failed",
    }:
        assert any(event["action"] == action for event in events)


@pytest.mark.unit
def test_hydrate_engines_from_db_updates_cs_tracker_when_two_performances_exist(monkeypatch):
    events = []
    cs_updates = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))
    from titan.science.critical_speed import CriticalSpeedEngine

    monkeypatch.setattr(
        CriticalSpeedEngine,
        "estimate_cs_and_dprime",
        staticmethod(lambda _dist_time: (4.1, 250.0)),
    )

    coach = _make_hydration_coach(
        _HydrationDB(
            cs=[
                ("2026-03-05", 5000.0, 1200.0),
                ("2026-03-01", 3000.0, 700.0),
            ]
        )
    )
    coach.cs_tracker = SimpleNamespace(confidence=1.0, archetype="stable", update=lambda *args: cs_updates.append(args))

    confidence = coach._hydrate_engines_from_db()

    assert confidence["cs"] is True
    assert cs_updates == [("2026-03-05", 4.1, 250.0)]
    assert any(event["action"] == "cs_hydrated" and event["performances"] == 2 for event in events)


@pytest.mark.unit
def test_hydrate_engines_from_db_cold_start_emits_low_confidence_warning(monkeypatch):
    events = []
    warning_messages = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))
    monkeypatch.setattr(daily_coach._log, "warning", lambda message: warning_messages.append(message))

    coach = _make_hydration_coach(_HydrationDB())

    confidence = coach._hydrate_engines_from_db()

    assert confidence == {"hrv": False, "weight": False, "load": False, "hrr": False, "cs": False, "freshness": True}
    assert coach._startup_hydration_confidence == confidence
    assert any(event["action"] == "startup_hydration_report" and event["confidence"] == confidence for event in events)
    assert any("startup_low_confidence" in message for message in warning_messages)


@pytest.mark.unit
def test_hydrate_engines_from_db_partial_hydration_no_low_confidence_warning(monkeypatch):
    events = []
    warning_messages = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))
    monkeypatch.setattr(daily_coach._log, "warning", lambda message: warning_messages.append(message))

    coach = _make_hydration_coach(
        _HydrationDB(
            hrv=[("2026-03-01", 42.0)],
            weight=[("2026-03-01", 70.0)],
            load=[("2026-03-01", 55.0)],
            hrr=[],
            cs=[],
        )
    )

    confidence = coach._hydrate_engines_from_db()

    assert confidence == {"hrv": True, "weight": True, "load": True, "hrr": False, "cs": False, "freshness": True}
    assert any(event["action"] == "startup_hydration_report" and event["confidence"] == confidence for event in events)
    assert warning_messages == []


@pytest.mark.unit
def test_daily_coach_init_emits_metrics_under_review_event(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))
    monkeypatch.setattr(daily_coach, "get_metrics_under_review", lambda: ["trimp", "efficiency_index"])
    monkeypatch.setattr(DailyCoach, "_hydrate_engines_from_db", lambda self: {"hrv": True})

    DailyCoach(
        garmin_sync=SimpleNamespace(),
        weather_api=SimpleNamespace(),
        telegram_bot=SimpleNamespace(),
        hrv_engine=SimpleNamespace(),
        tsb_engine=SimpleNamespace(),
        readiness_engine=SimpleNamespace(),
        optimal_time_calc=SimpleNamespace(),
        nutrition_optimizer=SimpleNamespace(),
        weekly_planner=SimpleNamespace(),
        db=DummyDB(),
        engines=_placeholder_engine_registry(),
        glycogen_accum=SimpleNamespace(),
        governance=SimpleNamespace(),
        volume_load_gauge=SimpleNamespace(),
        outcome_tracker=SimpleNamespace(),
    )

    assert any(
        event["action"] == "metrics_under_review"
        and event["metrics"] == ["trimp", "efficiency_index"]
        and event["count"] == 2
        for event in events
    )


@pytest.mark.unit
def test_hydrate_engines_from_db_full_hydration_no_low_confidence_warning(monkeypatch):
    warning_messages = []
    monkeypatch.setattr(daily_coach._log, "warning", lambda message: warning_messages.append(message))

    coach = _make_hydration_coach(
        _HydrationDB(
            hrv=[("2026-03-01", 42.0)],
            weight=[("2026-03-01", 70.0)],
            load=[("2026-03-01", 55.0)],
            hrr=[("2026-03-01", 20, 35)],
            cs=[("2026-03-01", 5000.0, 1200.0)],
        )
    )

    confidence = coach._hydrate_engines_from_db()

    assert confidence == {"hrv": True, "weight": True, "load": True, "hrr": True, "cs": True, "freshness": True}
    assert warning_messages == []


@pytest.mark.unit
def test_run_morning_routine_passes_data_confidence_low_only_on_first_routine(monkeypatch):
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach._startup_hydration_confidence = {"hrv": False, "weight": False, "load": False, "hrr": False, "cs": False}
    coach._startup_confidence_applies_next_routine = True

    captured_contexts = []

    def _apply_constraints(session_plan, context):
        captured_contexts.append(dict(context))
        return {**session_plan, "governance_locks_applied": [], "governance_clean": True}

    coach.governance = SimpleNamespace(
        apply_constraints=_apply_constraints,
        get_governance_report=lambda **k: {},
    )

    assert coach.run_morning_routine() is True
    assert coach.run_morning_routine() is True

    assert captured_contexts[0]["data_confidence_low"] is True
    assert "data_confidence_low" not in captured_contexts[1]


# ── T1-15: PersistenceFailure sentinel + degraded conservative mode ─────────

class _FailingTransactionDB(DummyDB):
    """DummyDB variant whose transaction() context manager always raises."""

    @contextmanager
    def transaction(self):
        raise sqlite3.OperationalError("disk I/O error")
        yield  # required for generator protocol


@pytest.mark.unit
def test_persist_garmin_data_rollback_raises_persistence_failure_with_defaults(monkeypatch):
    """When the DB transaction rolls back, PersistenceFailure is raised with default values
    and a PERSIST_ERROR step event is emitted (not SUCCESS)."""
    from titan.orchestration.daily_coach import PersistenceFailure

    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build()
    coach.db = _FailingTransactionDB()

    garmin_data = {
        "activities": [{"date": "2026-03-06", "session_type": "EASY", "distance_km": 5, "duration_sec": 1800}],
        "sleep": [],
        "hrv": [],
        "weight": [],
    }
    with pytest.raises(PersistenceFailure) as exc_info:
        coach._persist_garmin_data(garmin_data, "2026-03-06")

    pf = exc_info.value
    assert pf.today_rhr == 0
    assert pf.today_sleep_score == 50  # conservative default (< 70 → negative sleep_delta)
    assert pf.today_sleep_hours == 7.5

    persist_failed_events = [e for e in events if e.get("action") == "daily_metrics_persist_failed"]
    assert persist_failed_events, "daily_metrics_persist_failed event must be emitted"


@pytest.mark.unit
def test_run_morning_routine_persistence_failure_sets_degraded_flag(monkeypatch):
    """When step 2 raises PersistenceFailure, persistence_degraded=True must reach
    the governance context and the routine must complete successfully."""
    captured_contexts = []
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build()
    coach.db = _FailingTransactionDB()

    def _apply_constraints(session_plan, context):
        captured_contexts.append(dict(context))
        return {**session_plan, "governance_locks_applied": [], "governance_clean": True}

    coach.governance = SimpleNamespace(
        apply_constraints=_apply_constraints,
        get_governance_report=lambda **k: {},
    )

    result = coach.run_morning_routine()
    assert result is True
    assert captured_contexts, "governance context must be captured"
    assert captured_contexts[0].get("persistence_degraded") is True

    degraded_events = [e for e in events if e.get("action") == "persistence_degraded_mode"]
    assert degraded_events, "persistence_degraded_mode event must be emitted"


@pytest.mark.unit
def test_governance_engine_persistence_degraded_caps_intensity_at_easy():
    """GovernanceEngine must cap session intensity at EASY when persistence_degraded=True."""
    from titan.science.governance_engine import GovernanceEngine

    engine = GovernanceEngine()
    session_plan = {
        "session_type": "INTERVALS",
        "duration_min": 60,
        "max_zone": 5,
        "volume_pct": 1.0,
    }
    context = {
        "persistence_degraded": True,
        "afi_constraints": {"afi_modifier": 0, "readiness_clamp": 100},
        "intensity_gate_result": {"zone": "GREEN"},
        "readiness_score": 70.0,
        "glycogen_debt": 1.0,
        "fatigue_level": "LOW",
        "acwr": 1.0,
        "days_since_last_vo2": 5,
        "fueling_confirmed": True,
        "planned_duration_min": 60,
        "today_hrv": 45.0,
        "baseline_hrv": 40.0,
        "hrv_std_dev": 2.0,
        "today_rhr": 50,
        "baseline_rhr": 50.0,
        "sleep_score": 75,
        "subjective_fatigue_score": 4,
        "tsb_value": 5.0,
        "injury_flag": False,
        "priority_vector": {},
        "lock_thresholds": {},
    }
    result = engine.apply_constraints(session_plan=session_plan, context=context)
    assert result["session_type"] == "EASY"
    assert "PERSISTENCE_DEGRADED_CEILING" in result.get("governance_locks_applied", [])


@pytest.mark.unit
def test_run_morning_routine_persistence_failure_sends_telegram_alert(monkeypatch):
    """When step 2 raises PersistenceFailure, a Telegram alert must be sent."""
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: None)

    alert_messages = []
    coach = MinimalCoachFactory.build()
    coach.db = _FailingTransactionDB()
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: True,
        # Same signature as TitanTelegramBot.send_alert.
        send_alert=lambda title, message, level="warning": alert_messages.append(
            f"{title}: {message}"
        ),
    )

    coach.run_morning_routine()

    assert alert_messages, "Telegram alert must be sent on persistence failure"
    assert "Persistence failure" in alert_messages[0] or "persistence" in alert_messages[0].lower()


# ── T2-13: DegradedModeTracker ───────────────────────────────────────────────


@pytest.mark.unit
def test_degraded_tracker_sets_timestamp_on_first_failure():
    """When a flag becomes True for the first time, degraded_since is set."""
    tracker = DegradedModeTracker()
    tracker.update({"persistence_degraded": True}, alert_fn=lambda _: None)
    result = tracker.get_degraded_since()
    assert "persistence_degraded" in result
    assert result["persistence_degraded"] is not None


@pytest.mark.unit
def test_degraded_tracker_clears_on_recovery():
    """When a flag returns to False, degraded_since for that key is cleared."""
    tracker = DegradedModeTracker()
    tracker.update({"persistence_degraded": True}, alert_fn=lambda _: None)
    tracker.update({"persistence_degraded": False}, alert_fn=lambda _: None)
    result = tracker.get_degraded_since()
    assert "persistence_degraded" not in result


@pytest.mark.unit
def test_degraded_tracker_fires_alert_after_24h():
    """When degraded_since is older than 24h, send_alert must be called."""
    tracker = DegradedModeTracker()
    tracker.update({"persistence_degraded": True}, alert_fn=lambda _: None)

    # Backdate the degraded_since to 25 hours ago (UTC-aware, per HR-01)
    from datetime import UTC
    tracker._degraded_since["persistence_degraded"] = datetime.now(UTC) - timedelta(hours=25)

    alerts = []
    tracker.update({"persistence_degraded": True}, alert_fn=lambda msg: alerts.append(msg))

    assert alerts, "Alert must be fired after >24h in degraded mode"
    assert "persistence_degraded" in alerts[0]
    assert "25h" in alerts[0] or "h" in alerts[0]


@pytest.mark.unit
def test_run_morning_routine_surfaces_hrv_stress_context_in_telegram_payload():
    payload = {}
    coach = MinimalCoachFactory.build(telegram_success=True)

    def _governance_apply(*, session_plan, context):
        return {
            **session_plan,
            "session_type": "REST",
            "hrv_stress_context": "ILLNESS_PATTERN",
            "governance_locks_applied": ["HARD_STOP_SAFETY_GATES"],
            "governance_clean": False,
        }

    coach.governance = SimpleNamespace(
        apply_constraints=_governance_apply,
        get_governance_report=lambda **_kwargs: {},
    )
    coach.telegram = SimpleNamespace(send_daily_coaching=lambda data: payload.update(data) or True)

    assert coach.run_morning_routine() is True
    assert payload["hrv_stress_context"] == "ILLNESS_PATTERN"


@pytest.mark.unit
def test_run_morning_routine_propagates_data_trust_to_payload_and_context():
    captured_payload = {}
    captured_context = {}
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.db.get_last_sync_outcome = lambda source: {
        "last_success_ts": datetime.now(),
        "last_error_class": None,
    }

    def _governance_spy(session_plan, context):
        captured_context.update(context)
        return {**session_plan, "governance_locks_applied": [], "governance_clean": True}

    coach.governance = SimpleNamespace(
        apply_constraints=_governance_spy,
        get_governance_report=lambda **_k: {},
    )
    coach.optimal_time = SimpleNamespace(
        calculate_optimal_time=lambda **k: {
            "recommended_time": "06:30",
            "dew_point": 11,
            "quality": "🟩 EXCELLENT",
            "weather_data_quality": "live",
        }
    )
    coach.telegram = SimpleNamespace(send_daily_coaching=lambda payload: captured_payload.update(payload) or True)

    assert coach.run_morning_routine() is True
    assert captured_context["data_trust"]["overall"] == "TRUSTED"
    assert captured_payload["data_trust"]["overall"] == "TRUSTED"


@pytest.mark.unit
def test_run_morning_routine_adds_suspect_data_trust_caveat():
    captured_payload = {}
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.db.get_last_sync_outcome = lambda source: {
        "last_success_ts": datetime.now() - timedelta(hours=13),
        "last_error_class": None,
    }
    coach.optimal_time = SimpleNamespace(
        calculate_optimal_time=lambda **k: {
            "recommended_time": "06:30",
            "dew_point": 11,
            "quality": "🟩 EXCELLENT",
            "weather_data_quality": "live",
        }
    )
    coach.telegram = SimpleNamespace(send_daily_coaching=lambda payload: captured_payload.update(payload) or True)

    assert coach.run_morning_routine() is True
    assert captured_payload["data_trust"]["overall"] == "SUSPECT"
    assert "suspect" in captured_payload["special_note"].lower()


@pytest.mark.unit
def test_run_morning_routine_forwards_decision_rationale_into_telegram_payload():
    payload = {}
    coach = MinimalCoachFactory.build(telegram_success=True)

    coach.governance = SimpleNamespace(
        apply_constraints=lambda session_plan, context: {
            **session_plan,
            "governance_locks_applied": ["H1"],
            "governance_clean": False,
            "decision_rationale": {
                "primary_reason": "Injury flag active.",
                "actionable_guidance": "Take full rest.",
                "gate_findings": [{"gate": "H1", "status": "TRIGGERED"}],
            },
        },
        get_governance_report=lambda **_k: {},
    )
    coach.telegram = SimpleNamespace(send_daily_coaching=lambda data: payload.update(data) or True)

    assert coach.run_morning_routine() is True
    assert payload["primary_reason"] == "Injury flag active."
    assert payload["actionable_guidance"] == "Take full rest."


# ── B2 tests: _decision_pipeline() + _effect_runner() ───────────────────────


def _make_garmin_trust():
    from titan.science.data_trust import DataTrustLevel, DataTrustReport
    return DataTrustReport(
        source="garmin",
        trust_level=DataTrustLevel.TRUSTED,
        reasons=[],
        checked_at="2026-03-07T07:00:00+00:00",
        data_age_hours=0.5,
    )


def _pipeline_kwargs(coach):
    """Minimal valid keyword arguments for _decision_pipeline()."""
    return {
        "garmin_data": {
            "activities": [],
            "sleep": [{"restingHeartRate": 50, "sleepScores": {"overall": {"value": 80}}, "sleepTimeSeconds": 25200}],
            "hrv": [{"date": "2026-03-07", "rmssd": 45.0}],
            "hrr": [],
            "weight": [],
            "temperature_c": 20,
            "acwr": 1.0,
        },
        "soreness": 2,
        "subjective_fatigue_score": 2,
        "today_rhr": 50,
        "today_sleep_score": 80,
        "today_sleep_hours": 7.5,
        "baseline_rhr_for_comparison": 49.0,
        "persistence_degraded": False,
        "garmin_data_stale": False,
        "latest_hrv": 45.0,
        "baseline_hrv": 40.0,
        "hrv_summary": {"latest_hrv": 45.0, "baseline": 40.0, "trend": "steady", "std_dev": 1.0},
        "afi_final": 0.2,
        "afi_constraints": {"afi_modifier": 0, "readiness_clamp": 100},
        "tsb_value": 0.0,
        "tsb_status": "BALANCED",
        "cs_thermal": None,
        "garmin_trust": _make_garmin_trust(),
        "garmin_report_payload": {},
        "startup_hydration_confidence": {},
        "startup_confidence_applies": False,
    }


@pytest.mark.unit
def test_decision_pipeline_returns_decision_result():
    from titan.orchestration.contracts import DecisionResult

    coach = MinimalCoachFactory.build()
    result = coach._decision_pipeline(**_pipeline_kwargs(coach))

    assert isinstance(result, DecisionResult)
    assert isinstance(result.session_plan, dict)
    assert isinstance(result.coaching_payload, dict)
    assert isinstance(result.planned_effects, tuple)
    assert isinstance(result.decision_trace, dict)
    assert isinstance(result.snapshot_at, str)


@pytest.mark.unit
def test_decision_pipeline_no_db_writes():
    write_calls = []

    coach = MinimalCoachFactory.build()
    original_save_session = coach.db.save_session
    coach.db.save_session = lambda **kw: write_calls.append(("save_session", kw)) or original_save_session(**kw)
    coach.db.save_daily_metric = lambda **kw: write_calls.append(("save_daily_metric", kw))
    coach.db.update_glycogen_debt = lambda **kw: write_calls.append(("update_glycogen_debt", kw))

    coach._decision_pipeline(**_pipeline_kwargs(coach))

    assert write_calls == [], f"Pipeline made unexpected DB write(s): {write_calls}"


@pytest.mark.unit
def test_decision_pipeline_no_telegram_calls():
    telegram_calls = []

    coach = MinimalCoachFactory.build()
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: telegram_calls.append("send_daily_coaching") or True,
        send_alert=lambda msg: telegram_calls.append("send_alert"),
    )

    coach._decision_pipeline(**_pipeline_kwargs(coach))

    assert telegram_calls == [], f"Pipeline made unexpected Telegram call(s): {telegram_calls}"


@pytest.mark.unit
def test_decision_pipeline_decision_trace_has_required_fields():
    required_keys = {
        "hrv", "tsb", "acwr", "lock_codes_active",
        "session_planned_pre_governance", "locks_applied", "governance_clean",
        "phase", "vlg_color", "afi_value", "readiness_score", "glycogen_debt",
    }

    coach = MinimalCoachFactory.build()
    result = coach._decision_pipeline(**_pipeline_kwargs(coach))

    missing = required_keys - result.decision_trace.keys()
    assert not missing, f"decision_trace missing required keys: {missing}"


@pytest.mark.unit
def test_effect_runner_dispatches_record_outcome():
    from titan.orchestration.contracts import DecisionResult, PlannedEffect

    recorded = []
    coach = MinimalCoachFactory.build()
    coach.outcome_tracker = SimpleNamespace(record_decision=lambda **kw: recorded.append(kw))

    result = DecisionResult(
        session_plan={"session_type": "EASY", "duration_min": 45},
        coaching_payload={
            "session_type": "EASY", "duration": "45 min", "details": "", "governance_locks": [],
            "optimal_time": "07:00", "dew_point": 12.0, "conditions": "GOOD",
            "hrv_status": "STABLE", "hrv_value": 45.0, "hrv_baseline": 40.0,
            "afi": 0.2, "sleep_quality": 80, "sleep_hours": 7.5,
            "readiness_score": 60.0, "subjective_fatigue_score": 2,
            "fatigue_level": "LOW", "fatigue_tags": [], "tsb": 0.0,
            "tsb_status": "BALANCED", "cs_smoothed": None, "cs_thermal": None,
            "archetype": "stable", "glycogen_debt": 0.0, "glycogen_status": "LOW",
            "glycogen_protocol": {}, "electrolyte_alert": {}, "nutrition_plan": "N/A",
            "governance_report": {}, "intensity_gate_result": None,
            "fueling_gate": None, "vo2_eligibility": None,
        },
        planned_effects=(PlannedEffect(effect_type="record_outcome", payload={}),),
        decision_trace={
            "hrv": 45.0, "tsb": 0.0, "acwr": 1.0, "lock_codes_active": [],
            "session_planned_pre_governance": "EASY", "session_post_governance": "EASY",
            "locks_applied": [], "governance_clean": True, "phase": "BASE",
            "vlg_color": "GREEN", "afi_value": 0.2, "readiness_score": 60.0,
            "glycogen_debt": 0.0, "apl_result": {}, "persistence_degraded": False,
            "garmin_data_stale": False, "data_confidence_low": False,
        },
        snapshot_at="2026-03-07T07:00:00",
    )

    coach._effect_runner(result)

    assert len(recorded) == 1
    assert recorded[0]["session_planned"] == "EASY"
    assert recorded[0]["governance_clean"] is True


@pytest.mark.unit
def test_effect_runner_dispatches_send_telegram():
    from titan.orchestration.contracts import DecisionResult, PlannedEffect

    delivered = []
    coach = MinimalCoachFactory.build()
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: delivered.append(payload) or True,
        send_alert=lambda msg: None,
    )

    session_plan = {"session_type": "EASY", "duration_min": 45}
    coaching_payload = {
        "session_type": "EASY", "duration": "45 min", "details": "", "governance_locks": [],
        "optimal_time": "07:00", "dew_point": 12.0, "conditions": "GOOD",
        "hrv_status": "STABLE", "hrv_value": 45.0, "hrv_baseline": 40.0,
        "afi": 0.2, "sleep_quality": 80, "sleep_hours": 7.5,
        "readiness_score": 60.0, "subjective_fatigue_score": 2,
        "fatigue_level": "LOW", "fatigue_tags": [], "tsb": 0.0,
        "tsb_status": "BALANCED", "cs_smoothed": None, "cs_thermal": None,
        "archetype": "stable", "glycogen_debt": 0.0, "glycogen_status": "LOW",
        "glycogen_protocol": {}, "electrolyte_alert": {}, "nutrition_plan": "N/A",
        "governance_report": {}, "intensity_gate_result": None,
        "fueling_gate": None, "vo2_eligibility": None,
    }
    result = DecisionResult(
        session_plan=session_plan,
        coaching_payload=coaching_payload,
        planned_effects=(PlannedEffect(effect_type="send_telegram", payload={}),),
        decision_trace={
            "hrv": 45.0, "tsb": 0.0, "acwr": 1.0, "lock_codes_active": [],
            "session_planned_pre_governance": "EASY", "session_post_governance": "EASY",
            "locks_applied": [], "governance_clean": True, "phase": "BASE",
            "vlg_color": "GREEN", "afi_value": 0.2, "readiness_score": 60.0,
            "glycogen_debt": 0.0, "apl_result": {}, "persistence_degraded": False,
            "garmin_data_stale": False, "data_confidence_low": False,
        },
        snapshot_at="2026-03-07T07:00:00",
    )

    success = coach._effect_runner(result)

    assert success is True
    assert len(delivered) == 1
    assert delivered[0]["session_type"] == "EASY"


@pytest.mark.unit
def test_effect_runner_effects_execute_in_order():
    from titan.orchestration.contracts import DecisionResult, PlannedEffect

    execution_order = []
    coach = MinimalCoachFactory.build()
    coach.outcome_tracker = SimpleNamespace(
        record_decision=lambda **kw: execution_order.append("record_outcome")
    )
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: execution_order.append("send_telegram") or True,
        send_alert=lambda msg: None,
    )

    coaching_payload = {
        "session_type": "EASY", "duration": "45 min", "details": "", "governance_locks": [],
        "optimal_time": "07:00", "dew_point": 12.0, "conditions": "GOOD",
        "hrv_status": "STABLE", "hrv_value": 45.0, "hrv_baseline": 40.0,
        "afi": 0.2, "sleep_quality": 80, "sleep_hours": 7.5,
        "readiness_score": 60.0, "subjective_fatigue_score": 2,
        "fatigue_level": "LOW", "fatigue_tags": [], "tsb": 0.0,
        "tsb_status": "BALANCED", "cs_smoothed": None, "cs_thermal": None,
        "archetype": "stable", "glycogen_debt": 0.0, "glycogen_status": "LOW",
        "glycogen_protocol": {}, "electrolyte_alert": {}, "nutrition_plan": "N/A",
        "governance_report": {}, "intensity_gate_result": None,
        "fueling_gate": None, "vo2_eligibility": None,
    }
    result = DecisionResult(
        session_plan={"session_type": "EASY", "duration_min": 45},
        coaching_payload=coaching_payload,
        planned_effects=(
            PlannedEffect(effect_type="record_outcome", payload={}),
            PlannedEffect(effect_type="send_telegram", payload={}),
        ),
        decision_trace={
            "hrv": 45.0, "tsb": 0.0, "acwr": 1.0, "lock_codes_active": [],
            "session_planned_pre_governance": "EASY", "session_post_governance": "EASY",
            "locks_applied": [], "governance_clean": True, "phase": "BASE",
            "vlg_color": "GREEN", "afi_value": 0.2, "readiness_score": 60.0,
            "glycogen_debt": 0.0, "apl_result": {}, "persistence_degraded": False,
            "garmin_data_stale": False, "data_confidence_low": False,
        },
        snapshot_at="2026-03-07T07:00:00",
    )

    coach._effect_runner(result)

    assert execution_order == ["record_outcome", "send_telegram"]


@pytest.mark.unit
def test_run_morning_routine_delegates_pipeline_then_runner(monkeypatch):
    """run_morning_routine() must call _decision_pipeline() then _effect_runner()."""
    from titan.orchestration.contracts import DecisionResult, PlannedEffect

    call_log = []

    coach = MinimalCoachFactory.build()

    dummy_coaching_payload = {
        "session_type": "EASY", "duration": "45 min", "details": "", "governance_locks": [],
        "optimal_time": "07:00", "dew_point": 12.0, "conditions": "GOOD",
        "hrv_status": "STABLE", "hrv_value": 45.0, "hrv_baseline": 40.0,
        "afi": 0.2, "sleep_quality": 80, "sleep_hours": 7.5,
        "readiness_score": 60.0, "subjective_fatigue_score": 2,
        "fatigue_level": "LOW", "fatigue_tags": [], "tsb": 0.0,
        "tsb_status": "BALANCED", "cs_smoothed": None, "cs_thermal": None,
        "archetype": "stable", "glycogen_debt": 0.0, "glycogen_status": "LOW",
        "glycogen_protocol": {}, "electrolyte_alert": {}, "nutrition_plan": "N/A",
        "governance_report": {}, "intensity_gate_result": None,
        "fueling_gate": None, "vo2_eligibility": None,
    }
    dummy_result = DecisionResult(
        session_plan={"session_type": "EASY", "duration_min": 45},
        coaching_payload=dummy_coaching_payload,
        planned_effects=(PlannedEffect(effect_type="send_telegram", payload={}),),
        decision_trace={
            "hrv": 45.0, "tsb": 0.0, "acwr": 1.0, "lock_codes_active": [],
            "session_planned_pre_governance": "EASY", "session_post_governance": "EASY",
            "locks_applied": [], "governance_clean": True, "phase": "BASE",
            "vlg_color": "GREEN", "afi_value": 0.2, "readiness_score": 60.0,
            "glycogen_debt": 0.0, "apl_result": {}, "persistence_degraded": False,
            "garmin_data_stale": False, "data_confidence_low": False,
        },
        snapshot_at="2026-03-07T07:00:00",
    )

    monkeypatch.setattr(coach, "_decision_pipeline", lambda **kw: call_log.append("pipeline") or dummy_result)
    monkeypatch.setattr(coach, "_effect_runner", lambda result: call_log.append("runner") or True)

    coach.run_morning_routine()

    assert call_log == ["pipeline", "runner"]


# ---------------------------------------------------------------------------
# Fix 2: sync returns 0/0/0/0 → sync_ok=False, recorded as failed sync
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sync_ok_false_when_all_empty_lists_returned(monkeypatch):
    """When sync_all returns 0/0/0/0 (no timeout), sync_ok must be False and success=False recorded."""
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=True)
    # Override garmin to return empty data with no timeout status
    coach.garmin = SimpleNamespace(
        sync_all=lambda: {
            "activities": [],
            "sleep": [],
            "hrv": [],
            "hrr": [],
            "weight": [],
            "temperature_c": 20,
            "acwr": 1.0,
        }
    )
    # Add send_structured_alert stub so the staleness branch (if triggered) doesn't error
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: True,
        send_alert=lambda msg: None,
        send_structured_alert=lambda **kwargs: None,
    )

    result = coach.run_morning_routine()
    assert result is True

    # The DB must have recorded success=False for the garmin sync
    assert hasattr(coach.db, "_last_sync_outcome"), "record_sync_outcome must have been called"
    assert coach.db._last_sync_outcome["success"] is False, (
        "Empty 0/0/0/0 sync must be recorded as success=False"
    )
    assert coach.db._last_sync_outcome["error_class"] == "GARMIN_EMPTY_SYNC", (
        "error_class must be GARMIN_EMPTY_SYNC for empty-data failure"
    )


# ---------------------------------------------------------------------------
# T5-62 Part B — garmin_sync_empty event + regression guard
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sync_empty_emits_garmin_sync_empty_warning_event(monkeypatch):
    """B1: 0/0/0/0 sync with no timeout → 'garmin_sync_empty' WARNING event emitted."""
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.garmin = SimpleNamespace(
        sync_all=lambda: {
            "activities": [],
            "sleep": [],
            "hrv": [],
            "hrr": [],
            "weight": [],
            "temperature_c": 20,
            "acwr": 1.0,
        }
    )
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: True,
        send_alert=lambda msg: None,
        send_structured_alert=lambda **kwargs: None,
    )

    coach.run_morning_routine()

    empty_events = [e for e in events if e["action"] == "garmin_sync_empty"]
    assert empty_events, "'garmin_sync_empty' event must be emitted when sync returns 0/0/0/0"
    ev = empty_events[0]
    assert ev.get("severity") in ("WARNING", "warning", "EventSeverity.WARNING"), (
        "'garmin_sync_empty' event must carry severity=WARNING"
    )


@pytest.mark.unit
def test_sync_with_data_does_not_emit_garmin_sync_empty_event(monkeypatch):
    """B2: Regression guard — sync with data must NOT emit 'garmin_sync_empty' event."""
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.garmin = SimpleNamespace(
        sync_all=lambda: {
            "activities": [{"activityId": 1, "activityType": {"typeKey": "running"}, "distance": 10000, "duration": 3600, "averageHR": 150, "maxHR": 175, "startTimeLocal": "2026-03-28 07:00:00", "averageSpeed": 2.78}],
            "sleep": [],
            "hrv": [],
            "hrr": [],
            "weight": [],
            "temperature_c": 20,
            "acwr": 1.0,
        }
    )
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: True,
        send_alert=lambda msg: None,
        send_structured_alert=lambda **kwargs: None,
    )

    coach.run_morning_routine()

    empty_events = [e for e in events if e["action"] == "garmin_sync_empty"]
    assert not empty_events, "'garmin_sync_empty' must NOT be emitted when sync returns data"


class TestT5_51_AcwrNullPropagation:
    """T5-51: Missing ACWR must propagate as None, not silently default to 1.0 (sweet-spot)."""

    @pytest.mark.unit
    def test_vlg_receives_none_when_acwr_absent_from_garmin(self):
        """When garmin_data has no 'acwr' key, VLG.resolve must receive acwr=None (not 1.0)."""
        from types import SimpleNamespace
        coach = MinimalCoachFactory.build()
        coach.garmin = SimpleNamespace(
            sync_all=lambda: {
                "activities": [],
                "sleep": [{"restingHeartRate": 50, "sleepScores": {"overall": {"value": 80}}, "sleepTimeSeconds": 25200}],
                "hrv": [{"date": "2026-03-04", "rmssd": 45.0}],
                "hrr": [],
                "weight": [],
                "temperature_c": 20,
                # deliberately omit 'acwr'
            },
            is_api_degraded=False,
        )
        captured = {}

        def capturing_vlg_resolve(**kwargs):
            captured["acwr"] = kwargs.get("acwr")
            return SimpleNamespace(color="GREEN")

        coach.vlg = SimpleNamespace(resolve=capturing_vlg_resolve)
        coach.run_morning_routine()
        assert captured.get("acwr") is None  # must be None, NOT 1.0

    @pytest.mark.unit
    def test_record_decision_acwr_not_sweet_spot_when_absent(self):
        """When garmin_data has no 'acwr', record_decision must NOT receive acwr=1.0."""
        from types import SimpleNamespace
        coach = MinimalCoachFactory.build()
        coach.garmin = SimpleNamespace(
            sync_all=lambda: {
                "activities": [],
                "sleep": [{"restingHeartRate": 50, "sleepScores": {"overall": {"value": 80}}, "sleepTimeSeconds": 25200}],
                "hrv": [{"date": "2026-03-04", "rmssd": 45.0}],
                "hrr": [],
                "weight": [],
                "temperature_c": 20,
                # deliberately omit 'acwr'
            },
            is_api_degraded=False,
        )
        captured = {}
        coach.outcome_tracker = SimpleNamespace(
            record_decision=lambda **kwargs: captured.update({"acwr": kwargs.get("acwr")})
        )
        coach.run_morning_routine()
        assert captured.get("acwr") != 1.0  # must NOT be the sweet-spot

    @pytest.mark.unit
    def test_daily_coach_context_contract_accepts_none_acwr(self):
        """DailyCoachContextContract must accept acwr=None without error."""
        from titan.orchestration.contracts import DailyCoachContextContract
        contract = DailyCoachContextContract(
            db=object(),
            cs_tracker=object(),
            afi_constraints={},
            intensity_gate_result={},
            readiness_score=50.0,
            glycogen_debt=0.0,
            fatigue_level="LOW",
            acwr=None,
            days_since_last_vo2=None,
            fueling_confirmed=False,
            planned_duration_min=45,
            today_hrv=0.0,
            baseline_hrv=0.0,
            hrv_std_dev=0.0,
            today_rhr=0,
            baseline_rhr=0.0,
            sleep_score=0,
            subjective_fatigue_score=0,
            tsb_value=0.0,
            injury_flag=False,
            priority_vector={},
            lock_thresholds={},
        )
        assert contract.acwr is None


# ── T5-44: athlete_max_hr threading through DailyCoach → sync_all ────────────


@pytest.mark.unit
def test_daily_coach_passes_athlete_max_hr_to_garmin_sync_instance(monkeypatch):
    """DailyCoach.__init__(athlete_max_hr=185) must inject the value into
    garmin_sync.athlete_max_hr so that _sync_operation forwards it to
    sync_activities() during every sync_all() call.

    Verifies the injection chain:
    DailyCoach.__init__(athlete_max_hr=185)
      → garmin_sync.athlete_max_hr = 185
    """
    monkeypatch.setattr(DailyCoach, "_hydrate_engines_from_db", lambda self: {})
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda *a, **kw: None)

    fake_garmin = SimpleNamespace(
        sync_all=lambda: {},
        athlete_max_hr=0,   # starts at 0; must be overwritten by DailyCoach
    )

    coach = DailyCoach(
        garmin_sync=fake_garmin,
        weather_api=SimpleNamespace(),
        telegram_bot=SimpleNamespace(send_alert=lambda *a, **kw: None),
        hrv_engine=SimpleNamespace(),
        tsb_engine=SimpleNamespace(),
        readiness_engine=SimpleNamespace(),
        optimal_time_calc=SimpleNamespace(),
        nutrition_optimizer=SimpleNamespace(),
        weekly_planner=SimpleNamespace(),
        db=DummyDB(),
        engines=_placeholder_engine_registry(),
        athlete_max_hr=185,
    )

    assert coach.athlete_max_hr == 185
    # The injection is done via setattr — confirm the GarminSync instance was updated.
    assert fake_garmin.athlete_max_hr == 185


@pytest.mark.unit
def test_daily_coach_athlete_max_hr_defaults_to_zero():
    """When athlete_max_hr is not supplied, DailyCoach stores 0 (safe default)."""
    coach = DailyCoach(
        garmin_sync=SimpleNamespace(),
        weather_api=SimpleNamespace(),
        telegram_bot=SimpleNamespace(),
        hrv_engine=SimpleNamespace(),
        tsb_engine=SimpleNamespace(),
        readiness_engine=SimpleNamespace(),
        optimal_time_calc=SimpleNamespace(),
        nutrition_optimizer=SimpleNamespace(),
        weekly_planner=SimpleNamespace(),
        db=DummyDB(),
        engines=_placeholder_engine_registry(),
    )
    assert coach.athlete_max_hr == 0


# ─────────────────────────────────────────────────────────────────────────────
# T5-64 / OBS-029: cs_confidence absent → must default to 0.0, not 1.0
# CS_CONFIDENCE_LOCK must fire when cs_tracker has no confidence attribute.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_run_morning_routine_absent_cs_confidence_passes_zero_to_apl():
    """T5-64: cs_tracker without confidence attr → APL called with cs_confidence=0.0, not 1.0."""
    coach = MinimalCoachFactory.build(telegram_success=True)
    # cs_tracker without a 'confidence' attribute — simulates new/uncalibrated tracker.
    coach.cs_tracker = SimpleNamespace(
        apply_thermal=lambda *_: 1.0,
        archetype="stable",
        cs_smoothed=3.5,
        # 'confidence' attr intentionally absent
    )
    captured_kwargs = {}

    def _capture_apl_call(**kwargs):
        captured_kwargs.update(kwargs)
        return {"priority_vector": {}, "lock_thresholds": {}}

    coach.apl = SimpleNamespace(resolve=_capture_apl_call)

    assert coach.run_morning_routine() is True
    assert "cs_confidence" in captured_kwargs, "APL.resolve must receive cs_confidence"
    assert captured_kwargs["cs_confidence"] == pytest.approx(0.0), (
        "absent cs_tracker.confidence must default to 0.0, not 1.0 (OBS-029 fix)"
    )


@pytest.mark.unit
def test_cs_confidence_lock_fires_when_cs_tracker_confidence_absent():
    """T5-64: governance CS_CONFIDENCE_LOCK must fire when cs_confidence defaults to 0.0."""
    from titan.science.governance_engine import GovernanceEngine

    engine = GovernanceEngine()
    # Tracker without confidence attr — getattr default was 1.0 (bug), must be 0.0 (fix).
    cs_tracker_no_confidence = SimpleNamespace()

    result = engine.check_cs_confidence_lock(cs_tracker_no_confidence)
    assert result["locked"] is True, (
        "CS_CONFIDENCE_LOCK must fire when cs_tracker has no confidence attribute "
        "(getattr default must be 0.0, not 1.0)"
    )


# ---------------------------------------------------------------------------
# T5-71 — HD-08: persistence_degraded=True forces data_confidence_low=True
# ---------------------------------------------------------------------------

def _make_base_context_kwargs() -> dict:
    """Minimal valid kwargs for _build_daily_coach_context."""
    return {
        "afi_constraints": {"afi_modifier": 0},
        "intensity_gate": {"color": "GREEN"},
        "readiness_score": 75.0,
        "glycogen_debt": 10.0,
        "fatigue_level": "LOW",
        "acwr": 1.0,
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
        "planned_duration_min": 60,
        "today_hrv": 50.0,
        "baseline_hrv": 52.0,
        "hrv_std_dev": 3.0,
        "today_rhr": 50,
        "baseline_rhr": 50.0,
        "sleep_score": 80,
        "subjective_fatigue_score": 3,
        "tsb_value": 5.0,
        "injury_flag": False,
        "priority_vector": {},
        "lock_thresholds": {},
    }


@pytest.mark.unit
def test_build_daily_coach_context_persistence_degraded_sets_data_confidence_low():
    """T5-71: persistence_degraded=True must force data_confidence_low=True in the payload."""
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = object()
    coach.cs_tracker = object()

    context = coach._build_daily_coach_context(
        **_make_base_context_kwargs(),
        persistence_degraded=True,
    )

    assert context.get("persistence_degraded") is True
    assert context.get("data_confidence_low") is True, (
        "data_confidence_low must be True when persistence_degraded=True "
        "(DEC-036 / T5-71)"
    )


@pytest.mark.unit
def test_build_daily_coach_context_persistence_degraded_overrides_explicit_false():
    """T5-71: persistence_degraded=True overrides an explicit data_confidence_low=False."""
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = object()
    coach.cs_tracker = object()

    context = coach._build_daily_coach_context(
        **_make_base_context_kwargs(),
        persistence_degraded=True,
        data_confidence_low=False,
    )

    assert context.get("data_confidence_low") is True, (
        "persistence_degraded must override data_confidence_low=False "
        "(DEC-036 / T5-71)"
    )


@pytest.mark.unit
def test_build_daily_coach_context_no_persistence_degraded_leaves_data_confidence_low_unset():
    """T5-71: Without persistence_degraded, data_confidence_low must not be injected."""
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = object()
    coach.cs_tracker = object()

    context = coach._build_daily_coach_context(**_make_base_context_kwargs())

    assert "data_confidence_low" not in context, (
        "data_confidence_low must not appear in the payload when persistence_degraded "
        "is False and no explicit value is passed"
    )


@pytest.mark.unit
def test_build_daily_coach_context_persistence_degraded_false_does_not_set_data_confidence_low():
    """T5-71: persistence_degraded=False must not force data_confidence_low=True."""
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = object()
    coach.cs_tracker = object()

    context = coach._build_daily_coach_context(
        **_make_base_context_kwargs(),
        persistence_degraded=False,
    )

    assert context.get("data_confidence_low") is not True, (
        "data_confidence_low must not be forced True when persistence_degraded=False"
    )


# ---------------------------------------------------------------------------
# Audit 2026-04-26: Step 8 + Step 10 ESI TypeError fallback and dew-point
# propagation tests (TASK 6)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_step8_planned_session_engine_exception_falls_to_conservative_mode(monkeypatch):
    """Step 8: TypeError('unexpected keyword argument') from get_today_session()
    triggers the ESI-less fallback call; routine completes and step 8 emits SUCCESS."""
    events: list[dict] = []
    monkeypatch.setattr(
        daily_coach,
        "_daily_coach_event",
        lambda action, **fields: events.append({"action": action, **fields}),
    )

    coach = MinimalCoachFactory.build(telegram_success=True)
    fallback_calls: list[str] = []

    def _planner(**kwargs):
        if kwargs:
            raise TypeError(
                "get_today_session() got an unexpected keyword argument 'esi_level'"
            )
        fallback_calls.append("no_args")
        return {"session_type": "EASY", "volume_pct": 1.0, "duration_min": 45, "distance_km": 8}

    coach.weekly_planner = SimpleNamespace(get_today_session=_planner)

    assert coach.run_morning_routine() is True
    assert fallback_calls == ["no_args"], "no-args fallback must be called exactly once"
    assert any(
        e["action"] == "step_event"
        and e["step_number"] == 8
        and e["outcome"] == "SUCCESS"
        for e in events
    ), "Step 8 must emit SUCCESS after the ESI-TypeError fallback"


@pytest.mark.unit
def test_step8_planned_session_missing_athlete_profile_returns_safe_default(monkeypatch):
    """Step 8: when get_today_session() returns {} (no athlete profile configured),
    the routine completes using .get() safe defaults and step 8 emits SUCCESS."""
    events: list[dict] = []
    monkeypatch.setattr(
        daily_coach,
        "_daily_coach_event",
        lambda action, **fields: events.append({"action": action, **fields}),
    )

    coach = MinimalCoachFactory.build(telegram_success=True)
    # Planner accepts ESI kwargs but returns empty dict (no plan for athlete)
    coach.weekly_planner = SimpleNamespace(get_today_session=lambda **k: {})

    assert coach.run_morning_routine() is True
    assert any(
        e["action"] == "step_event"
        and e["step_number"] == 8
        and e["outcome"] == "SUCCESS"
        for e in events
    ), "Step 8 must succeed even when the session dict is empty (safe .get() defaults apply)"


@pytest.mark.unit
def test_step10_optimal_time_weather_unavailable_uses_fallback_window(monkeypatch):
    """Step 10: TypeError('unexpected keyword argument') from calculate_optimal_time()
    triggers the ESI-less fallback call; routine completes and step 10 emits SUCCESS."""
    events: list[dict] = []
    monkeypatch.setattr(
        daily_coach,
        "_daily_coach_event",
        lambda action, **fields: events.append({"action": action, **fields}),
    )

    coach = MinimalCoachFactory.build(telegram_success=True)
    fallback_calls: list[str] = []

    def _calc_optimal(**kwargs):
        if "esi_level" in kwargs:
            raise TypeError(
                "calculate_optimal_time() got an unexpected keyword argument 'esi_level'"
            )
        fallback_calls.append("no_esi")
        return {
            "recommended_time": "07:00",
            "dew_point": 12,
            "quality": "GOOD",
            "weather_data_quality": "live",
        }

    coach.optimal_time = SimpleNamespace(calculate_optimal_time=_calc_optimal)

    assert coach.run_morning_routine() is True
    assert fallback_calls == ["no_esi"], "no-ESI-args fallback must be called exactly once"
    assert any(
        e["action"] == "step_event"
        and e["step_number"] == 10
        and e["outcome"] == "SUCCESS"
        for e in events
    ), "Step 10 must emit SUCCESS after the ESI-TypeError fallback"


@pytest.mark.unit
def test_step10_optimal_time_dew_point_above_threshold_pushes_session_window():
    """Step 10: garmin data with temperature_c=28, dew_point=22 produces ESI EXTREME
    (score=39 >= ESI_EXTREME_MIN=28); telegram payload carries esi_level='EXTREME'
    and a 25 s/km pace adjustment annotation."""
    payload: dict = {}

    coach = MinimalCoachFactory.build(telegram_success=True)

    # temperature_c=28, dew_point=22 → score = 28 + 0.5×22 = 39 ≥ ESI_EXTREME_MIN(28)
    coach.garmin = SimpleNamespace(
        sync_all=lambda: {
            "activities": [],
            "sleep": [
                {
                    "restingHeartRate": 50,
                    "sleepScores": {"overall": {"value": 80}},
                    "sleepTimeSeconds": 25200,
                }
            ],
            "hrv": [{"date": "2026-03-04", "rmssd": 45.0}],
            "hrr": [],
            "weight": [],
            "temperature_c": 28.0,
            "dew_point": 22.0,
            "acwr": 1.0,
        }
    )
    # calculate_optimal_time accepts all kwargs (no fallback needed for this test)
    coach.optimal_time = SimpleNamespace(
        calculate_optimal_time=lambda **k: {
            "recommended_time": "06:00",
            "dew_point": 22,
            "quality": "EXTREME HEAT",
            "weather_data_quality": "live",
        }
    )
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda p: payload.update(p) or True,
        send_alert=lambda msg: None,
    )

    assert coach.run_morning_routine() is True
    assert payload.get("esi_level") == "EXTREME", (
        f"expected esi_level='EXTREME', got {payload.get('esi_level')!r}"
    )
    assert payload.get("esi_pace_adjustment_sec_per_km") == 25, (
        f"expected 25 s/km adjustment, got {payload.get('esi_pace_adjustment_sec_per_km')!r}"
    )
    assert "+25s/km" in (payload.get("adjusted_target") or ""), (
        f"adjusted_target must include '+25s/km', got {payload.get('adjusted_target')!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# DB injection: _hydrate_engines_from_db must read from the injected db,
# never from a freshly created DatabaseManager() with a default path.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_daily_coach_uses_injected_db(tmp_path, monkeypatch):
    """TSBEngine must be loaded from the injected db, not a default-path DatabaseManager."""
    from titan.science.tsb_engine import TSBEngine

    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda *a, **kw: None)
    monkeypatch.setattr(daily_coach, "get_metrics_under_review", lambda: [])

    db = DatabaseManager(db_name="injection_test.db", db_dir=tmp_path)
    today = datetime.now()
    for i in range(30):
        day = (today - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        db.save_session(
            date=day,
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            training_load=55,
            athlete_id="owner",
        )

    tsb = TSBEngine()
    stub = SimpleNamespace(
        hrv_log=[],
        add_hrv_measurement=lambda *a, **kw: None,
        check_baseline_drift=lambda **kw: False,
        add_weight_entry=lambda *a, **kw: None,
        add_hrr=lambda *a, **kw: None,
        sync_all=lambda: {},
        athlete_max_hr=0,
        send_alert=lambda **kw: None,
    )
    cs = SimpleNamespace(update=lambda *a, **kw: None, confidence=0.0, archetype="unknown")
    ot = SimpleNamespace(record_decision=lambda **kw: None)

    coach = DailyCoach(
        garmin_sync=stub,
        weather_api=stub,
        telegram_bot=stub,
        hrv_engine=stub,
        tsb_engine=tsb,
        readiness_engine=stub,
        optimal_time_calc=stub,
        nutrition_optimizer=stub,
        weekly_planner=stub,
        db=db,
        engines=_placeholder_engine_registry(tsb=tsb, hrv=stub, readiness=stub, autonomic=stub, fatigue=stub, apl=stub, cs_tracker=cs),
        glycogen_accum=stub,
        governance=stub,
        volume_load_gauge=stub,
        outcome_tracker=ot,
    )

    assert len(tsb.daily_loads) == 30, (
        f"TSBEngine loaded {len(tsb.daily_loads)} entries from injected db; expected 30"
    )
    assert coach._startup_hydration_confidence.get("load") is True
    db.close()


@pytest.mark.unit
def test_tsb_loads_in_asc_order(monkeypatch):
    from titan.science.tsb_engine import TSBEngine

    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda *_a, **_k: None)

    base = datetime(2026, 5, 11).date()
    loads_asc = [
        ((base + timedelta(days=i)).isoformat(), float((i + 1) * 10))
        for i in range(10)
    ]

    tsb = TSBEngine()
    coach = _make_hydration_coach(_HydrationDB(load=loads_asc))
    coach.tsb = tsb

    coach._hydrate_engines_from_db()

    assert tsb.daily_loads[0] == (loads_asc[0][0], 10.0), (
        f"oldest entry expected first; got {tsb.daily_loads[0]}"
    )
    ctl = tsb.calculate_ctl()
    assert ctl is not None, "CTL must be non-None after hydration with valid loads"
