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

    def update_glycogen_debt(self, *args, **kwargs):
        return None

    def get_baseline_rhr(self, days: int = 7):
        return None

    def get_hrv_history(self, days: int = 14):
        return []

    def get_weight_history(self, days: int = 30):
        return []

    def get_training_load_history(self, days: int = 42):
        return []

    def get_hrr_history(self, days: int = 28):
        return []

    def get_cs_performances(self, limit: int = 10):
        return []

    def record_sync_outcome(self, **kwargs):
        self._last_sync_outcome = kwargs

    def get_last_sync_outcome(self, source: str):
        return None


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
            add_hrv_measurement=lambda *a, **k: None,
            calculate_ln_rmssd_deviation=lambda **k: 0.0,
            get_hrv_summary=lambda: {"latest_hrv": 45.0, "baseline": 40.0, "trend": "steady", "std_dev": 1.0},
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
        coach._degraded_tracker = DegradedModeTracker()
        coach.optimal_time = SimpleNamespace(calculate_optimal_time=lambda **k: {"recommended_time": "07:00", "dew_point": 12, "quality": "GOOD"})
        coach.nutrition = SimpleNamespace(
            analyze_weight_trend=lambda: {"current_weight": 70.0},
            add_weight_entry=lambda *a, **k: None,
            calculate_daily_nutrition=lambda **k: {"carbs_g": 250, "protein_g": 120},
        )
        coach.telegram = SimpleNamespace(
            send_daily_coaching=lambda payload: telegram_success,
            send_alert=lambda msg: None,
        )
        return coach


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


def test_run_morning_routine_async_starts_thread_when_idle(monkeypatch):
    coach = DailyCoach.__new__(DailyCoach)
    coach.run_morning_routine = lambda: True

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

    coach.run_morning_routine_async(trigger_source="scheduler")

    assert len(created_threads) == 1
    assert created_threads[0].name == "DailyCoachRoutine"
    assert created_threads[0].daemon is True
    assert created_threads[0].started is True
    assert coach._routine_thread is created_threads[0]
    assert coach._routine_started_monotonic == 123.45


def test_run_morning_routine_async_skips_when_thread_already_alive(monkeypatch):
    events = []
    coach = DailyCoach.__new__(DailyCoach)

    class AliveThread:
        name = "ExistingRoutine"

        @staticmethod
        def is_alive():
            return True

    coach._routine_thread = AliveThread()
    coach._routine_started_monotonic = 987.6

    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))
    monkeypatch.setattr(
        daily_coach.threading,
        "Thread",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Thread should not be created on overlap")),
    )

    coach.run_morning_routine_async(trigger_source="telegram_poll")

    assert events == [
        {
            "action": "routine_skipped_overlap",
            "trigger_source": "telegram_poll",
            "running_since": 987.6,
            "thread_name": "ExistingRoutine",
        }
    ]


def test_daily_coach_no_overlap_guard():
    coach = DailyCoach.__new__(DailyCoach)
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


def test_daily_coach_routine_thread_shutdown(tmp_path):
    coach = DailyCoach.__new__(DailyCoach)
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


def test_get_baseline_rhr_happy_path_returns_average():
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = SimpleNamespace(get_baseline_rhr=lambda days=7: 51.3)

    assert coach._get_baseline_rhr(days=7) == 51.3


def test_get_baseline_rhr_error_emits_unavailable_and_returns_none(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = DailyCoach.__new__(DailyCoach)

    def _raise_value_error(days=7):
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
        "esi_level",
        "esi_pace_adjustment_sec_per_km",
    }



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
    assert payload["sleep_quality"] == 75
    assert payload["sleep_hours"] == 7.5


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


def test_run_morning_routine_weekly_planner_exception_bubbles_with_engine_failure_event(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.weekly_planner = SimpleNamespace(
        get_today_session=lambda: (_ for _ in ()).throw(RuntimeError("planner_offline"))
    )

    with pytest.raises(RuntimeError, match="planner_offline"):
        coach.run_morning_routine()

    assert any(
        event["action"] == "step_event"
        and event["step_number"] == 8
        and event["outcome"] == "FAILED"
        and event["failure_class"] == daily_coach.ENGINE_ERROR
        for event in events
    )


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


def test_get_recent_trimp_prefers_trimp_and_falls_back_to_training_load():
    coach = DailyCoach.__new__(DailyCoach)

    total = coach._get_recent_trimp(
        [
            {"trimp": 75.5},
            {"trimp": 0, "training_load": 100},
        ]
    )

    assert total == 135.5


def test_feed_load_engines_rehydrates_tsb_in_oldest_first_order(monkeypatch):
    events = []
    added = []
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = SimpleNamespace(
        get_training_load_history=lambda days=42: [
            ("2026-03-04", 80.0),
            ("2026-03-03", 70.0),
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
    coach.db.save_hrr = lambda date, hrr_60, hrr_120: save_hrr_calls.append((date, hrr_60, hrr_120))
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
    coach.hrv = SimpleNamespace(hrv_log=[], add_hrv_measurement=lambda *_: None)
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

    def get_hrv_history(self, days=14):
        return self._hrv

    def get_weight_history(self, days=30):
        return self._weight

    def get_training_load_history(self, days=42):
        return self._load

    def get_hrr_history(self, days=28):
        return self._hrr

    def get_cs_performances(self, limit=10):
        return self._cs


class _HydrationFailureDB:
    def __getattr__(self, _name):
        raise RuntimeError("hydrate_failure")


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
        autonomic_engine=SimpleNamespace(),
        cs_tracker=SimpleNamespace(),
        glycogen_accum=SimpleNamespace(),
        governance=SimpleNamespace(),
        fatigue_engine=SimpleNamespace(),
        apl=SimpleNamespace(),
        volume_load_gauge=SimpleNamespace(),
        outcome_tracker=SimpleNamespace(),
    )

    assert any(
        event["action"] == "metrics_under_review"
        and event["metrics"] == ["trimp", "efficiency_index"]
        and event["count"] == 2
        for event in events
    )


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
    assert pf.today_sleep_score == 75
    assert pf.today_sleep_hours == 7.5

    persist_failed_events = [e for e in events if e.get("action") == "daily_metrics_persist_failed"]
    assert persist_failed_events, "daily_metrics_persist_failed event must be emitted"


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


def test_run_morning_routine_persistence_failure_sends_telegram_alert(monkeypatch):
    """When step 2 raises PersistenceFailure, a Telegram alert must be sent."""
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: None)

    alert_messages = []
    coach = MinimalCoachFactory.build()
    coach.db = _FailingTransactionDB()
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: True,
        send_alert=lambda msg: alert_messages.append(msg),
    )

    coach.run_morning_routine()

    assert alert_messages, "Telegram alert must be sent on persistence failure"
    assert "Persistence failure" in alert_messages[0] or "persistence" in alert_messages[0].lower()


# ── T2-13: DegradedModeTracker ───────────────────────────────────────────────


def test_degraded_tracker_sets_timestamp_on_first_failure():
    """When a flag becomes True for the first time, degraded_since is set."""
    tracker = DegradedModeTracker()
    tracker.update({"persistence_degraded": True}, alert_fn=lambda _: None)
    result = tracker.get_degraded_since()
    assert "persistence_degraded" in result
    assert result["persistence_degraded"] is not None


def test_degraded_tracker_clears_on_recovery():
    """When a flag returns to False, degraded_since for that key is cleared."""
    tracker = DegradedModeTracker()
    tracker.update({"persistence_degraded": True}, alert_fn=lambda _: None)
    tracker.update({"persistence_degraded": False}, alert_fn=lambda _: None)
    result = tracker.get_degraded_since()
    assert "persistence_degraded" not in result


def test_degraded_tracker_fires_alert_after_24h():
    """When degraded_since is older than 24h, send_alert must be called."""
    tracker = DegradedModeTracker()
    tracker.update({"persistence_degraded": True}, alert_fn=lambda _: None)

    # Backdate the degraded_since to 25 hours ago
    tracker._degraded_since["persistence_degraded"] = datetime.utcnow() - timedelta(hours=25)

    alerts = []
    tracker.update({"persistence_degraded": True}, alert_fn=lambda msg: alerts.append(msg))

    assert alerts, "Alert must be fired after >24h in degraded mode"
    assert "persistence_degraded" in alerts[0]
    assert "25h" in alerts[0] or "h" in alerts[0]


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


def test_decision_pipeline_no_db_writes():
    write_calls = []

    coach = MinimalCoachFactory.build()
    original_save_session = coach.db.save_session
    coach.db.save_session = lambda **kw: write_calls.append(("save_session", kw)) or original_save_session(**kw)
    coach.db.save_daily_metric = lambda **kw: write_calls.append(("save_daily_metric", kw))
    coach.db.update_glycogen_debt = lambda **kw: write_calls.append(("update_glycogen_debt", kw))

    coach._decision_pipeline(**_pipeline_kwargs(coach))

    assert write_calls == [], f"Pipeline made unexpected DB write(s): {write_calls}"


def test_decision_pipeline_no_telegram_calls():
    telegram_calls = []

    coach = MinimalCoachFactory.build()
    coach.telegram = SimpleNamespace(
        send_daily_coaching=lambda payload: telegram_calls.append("send_daily_coaching") or True,
        send_alert=lambda msg: telegram_calls.append("send_alert"),
    )

    coach._decision_pipeline(**_pipeline_kwargs(coach))

    assert telegram_calls == [], f"Pipeline made unexpected Telegram call(s): {telegram_calls}"


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
