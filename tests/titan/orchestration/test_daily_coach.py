import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from time import sleep
from types import SimpleNamespace

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration import daily_coach
from titan.orchestration.daily_coach import DailyCoach


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
        coach.optimal_time = SimpleNamespace(calculate_optimal_time=lambda **k: {"recommended_time": "07:00", "dew_point": 12, "quality": "GOOD"})
        coach.nutrition = SimpleNamespace(
            analyze_weight_trend=lambda: {"current_weight": 70.0},
            add_weight_entry=lambda *a, **k: None,
            calculate_daily_nutrition=lambda **k: {"carbs_g": 250, "protein_g": 120},
        )
        coach.telegram = SimpleNamespace(send_daily_coaching=lambda payload: telegram_success)
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


def test_persist_garmin_data_failure_mid_loop_rolls_back_entire_day(tmp_path):
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
        coach._persist_garmin_data(_garmin_payload_for_day(day), day)

        assert _count_rows(db, "training_log", day) == 0
        assert _count_rows(db, "daily_metrics", day) == 0
    finally:
        db.close()


def test_persist_garmin_data_failure_during_daily_metric_rolls_back_activities(tmp_path):
    class MetricFailDB(DatabaseManager):
        def save_daily_metric(self, **kwargs):
            raise RuntimeError("metric_failure")

    db = MetricFailDB(db_name="atomic_metric_fail.db", db_dir=tmp_path)
    coach = _build_atomic_persist_coach(db)
    day = "2026-03-04"

    try:
        coach._persist_garmin_data(_garmin_payload_for_day(day), day)

        assert _count_rows(db, "training_log", day) == 0
        assert _count_rows(db, "daily_metrics", day) == 0
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


def test_hydrate_engines_from_db_cold_start_emits_low_confidence_warning(monkeypatch):
    events = []
    warning_messages = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))
    monkeypatch.setattr(daily_coach._log, "warning", lambda message: warning_messages.append(message))

    coach = _make_hydration_coach(_HydrationDB())

    confidence = coach._hydrate_engines_from_db()

    assert confidence == {"hrv": False, "weight": False, "load": False, "hrr": False, "cs": False}
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

    assert confidence == {"hrv": True, "weight": True, "load": True, "hrr": False, "cs": False}
    assert any(event["action"] == "startup_hydration_report" and event["confidence"] == confidence for event in events)
    assert warning_messages == []


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

    assert confidence == {"hrv": True, "weight": True, "load": True, "hrr": True, "cs": True}
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
