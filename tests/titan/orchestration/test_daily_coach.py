from types import SimpleNamespace

import pytest

from titan.orchestration import daily_coach
from titan.orchestration.daily_coach import DailyCoach


class DummyDB:
    def __init__(self) -> None:
        self._save_calls = 0
        self.conn = SimpleNamespace(cursor=lambda: None)

    def save_session(self, **kwargs):
        self._save_calls += 1
        if self._save_calls == 2:
            raise RuntimeError("session_persist_failed")

    def save_daily_metric(self, **kwargs):
        return None

    def save_hrr(self, *args, **kwargs):
        return None

    def update_glycogen_debt(self, *args, **kwargs):
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


def test_persist_path_emits_activity_persisted_and_skipped(monkeypatch):
    events = []
    monkeypatch.setattr(daily_coach, "_daily_coach_event", lambda action, **fields: events.append({"action": action, **fields}))

    coach = MinimalCoachFactory.build()
    coach.db.save_daily_metric = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("metric_write_failed"))

    coach._persist_garmin_data(
        {
            "activities": [
                {"date": "2026-03-04", "session_type": "EASY", "distance_km": 5, "duration_sec": 1800},
                {"date": "2026-03-04", "session_type": "EASY", "distance_km": 3, "duration_sec": 1200},
            ],
            "sleep": [],
            "hrv": [],
            "weight": [],
        },
        "2026-03-04",
    )

    outcomes = {event.get("outcome") for event in events if event.get("action") == "activity_persist"}
    assert "ACTIVITY_PERSISTED" in outcomes
    assert "ACTIVITY_SKIPPED" in outcomes
    assert "DAILY_METRICS_SKIPPED" in outcomes


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
