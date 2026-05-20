import ast
import logging
from pathlib import Path

import pytest

from titan import main as titan_main


def _main_print_calls():
    source = Path("titan/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
    ]


def _print_call_function_names(print_calls):
    names = []
    for node in print_calls:
        parent = node
        while parent is not None and not isinstance(parent, ast.FunctionDef):
            parent = getattr(parent, "parent", None)
        names.append(parent.name if parent is not None else None)
    return names


def _attach_parents(tree):
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node


class _DummyGarmin:
    def __init__(self):
        self.stop_calls = 0

    def start_background_sync(self, interval_hours):
        return None

    def stop_background_sync(self):
        self.stop_calls += 1


class _DummyWeather:
    def __init__(self):
        self.stop_calls = 0

    def start_background_updates(self, interval_hours):
        return None

    def stop_background_updates(self):
        self.stop_calls += 1


class _DummyTelegram:
    def __init__(self):
        self.commands = {}
        self.scheduled_tasks = []
        self.sent_weekly_plans = []
        self.stop_calls = 0

    def register_command(self, name, callback):
        self.commands[name] = callback

    def start_bot(self):
        return None

    def stop_bot(self):
        self.stop_calls += 1

    def schedule_task(self, **kwargs):
        self.scheduled_tasks.append(kwargs)
        return

    def send_weekly_plan(self, plan):
        self.sent_weekly_plans.append(plan)
        return


class _DummyWeeklyPlanner:
    def __init__(self, *args, **kwargs):
        self.calls = []
        return

    def generate_weekly_plan(self, athlete_profile, phase):
        self.calls.append({"athlete_profile": athlete_profile, "phase": phase})
        return {"status": "ok"}


class _DummyDailyCoach:
    def __init__(self, *args, **kwargs):
        self.morning_calls = 0
        return

    def run_morning_routine_async(self):
        self.morning_calls += 1
        return


class _DummyDatabase:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def get_training_load_history(self, days=42):
        return []


class _DummyTitanContextContract:
    def __init__(self, **payload):
        self.payload = payload

    def to_payload(self):
        return self.payload


def _patch_main_dependencies(monkeypatch):
    monkeypatch.setattr(titan_main, "_print_banner", lambda: None)
    monkeypatch.setattr(titan_main, "ensure_credentials", lambda: True)

    dummy_garmin = _DummyGarmin()
    dummy_weather = _DummyWeather()
    dummy_telegram = _DummyTelegram()
    dummy_db = _DummyDatabase()
    dummy_daily_coach = _DummyDailyCoach()
    dummy_weekly_planner = _DummyWeeklyPlanner()

    monkeypatch.setattr(titan_main, "GarminSync", lambda: dummy_garmin)
    monkeypatch.setattr(titan_main, "TitanTelegramBot", lambda: dummy_telegram)
    monkeypatch.setattr(titan_main, "DatabaseManager", lambda: dummy_db)
    monkeypatch.setattr(titan_main, "DailyCoach", lambda **kwargs: dummy_daily_coach)
    monkeypatch.setattr(titan_main, "WeeklyPlanGenerator", lambda *args, **kwargs: dummy_weekly_planner)
    monkeypatch.setattr(titan_main, "OptimalTimeCalculator", lambda weather: object())
    monkeypatch.setattr(titan_main, "NutritionOptimizer", lambda glycogen_model: object())
    monkeypatch.setattr(titan_main, "TitanContextContract", _DummyTitanContextContract)

    monkeypatch.setattr(titan_main, "HRVGuidedEngine", lambda: object())
    monkeypatch.setattr(titan_main, "TSBEngine", lambda: object())
    monkeypatch.setattr(titan_main, "ACWREngine", lambda: object())
    monkeypatch.setattr(titan_main, "ReadinessEngine", lambda: object())
    monkeypatch.setattr(titan_main, "GlycogenModel", lambda: object())
    monkeypatch.setattr(titan_main, "DriftEngine", lambda: object())
    monkeypatch.setattr(titan_main, "LactateLogic", lambda: object())
    monkeypatch.setattr(titan_main, "TRIMPEngine", lambda: object())
    monkeypatch.setattr(titan_main, "FatigueEngine", lambda: object())
    monkeypatch.setattr(titan_main, "AdaptiveMemory", lambda: object())
    monkeypatch.setattr(titan_main, "BiomechanicsAnalysis", lambda: object())
    monkeypatch.setattr(titan_main, "EfficiencyEngine", lambda: object())
    monkeypatch.setattr(titan_main, "DurabilityEngine", lambda: object())
    monkeypatch.setattr(titan_main, "CriticalSpeedEngine", lambda: object())
    monkeypatch.setattr(titan_main, "RCPEngine", lambda: object())

    weather_module = type("WeatherModule", (), {"WeatherAPI": lambda: dummy_weather})
    import sys

    monkeypatch.setitem(sys.modules, "titan.integrations.weather_api", weather_module)

    return dummy_garmin, dummy_weather, dummy_telegram, dummy_db, dummy_daily_coach, dummy_weekly_planner


def test_parse_env_number_happy_path(monkeypatch):
    monkeypatch.setenv("ATHLETE_AGE", "36")

    value = titan_main._parse_env_number("ATHLETE_AGE", "35", int)

    assert value == 36


def test_parse_env_number_invalid_value_logs_and_exits(monkeypatch, caplog):
    monkeypatch.setenv("ATHLETE_WEIGHT", "not-a-number")

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
        titan_main._parse_env_number("ATHLETE_WEIGHT", "75", float)

    record = next(r for r in caplog.records if r.msg == "startup_failure")
    assert record.component == "launcher"
    assert record.error_class == "ValueError"
    assert "ATHLETE_WEIGHT='not-a-number'" in record.detail


def test_main_credentials_failure_logs_structured_startup_event(monkeypatch, caplog):
    monkeypatch.setattr(titan_main, "_print_banner", lambda: None)
    monkeypatch.setattr(titan_main, "ensure_credentials", lambda: False)

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
        titan_main.main()

    record = next(r for r in caplog.records if r.msg == "startup_failure")
    assert record.component == "launcher"
    assert record.error_class == "CredentialsUnavailable"
    assert record.detail == "ensure_credentials() returned False"


def test_main_keyboard_interrupt_logs_shutdown_and_cleans_up(monkeypatch, caplog):
    garmin, weather, telegram, db, _daily_coach, _weekly_planner = _patch_main_dependencies(monkeypatch)
    monkeypatch.setattr(titan_main, "main_menu", lambda _: (_ for _ in ()).throw(KeyboardInterrupt))

    with caplog.at_level(logging.INFO):
        titan_main.main()

    record = next(r for r in caplog.records if r.msg == "shutdown_requested")
    assert record.reason == "keyboard_interrupt"
    assert record.timestamp
    assert garmin.stop_calls == 1
    assert weather.stop_calls == 1
    assert telegram.stop_calls == 1
    assert db.closed is True


def test_main_normal_exit_runs_clean_shutdown_without_shutdown_log(monkeypatch, caplog):
    garmin, weather, telegram, db, _daily_coach, _weekly_planner = _patch_main_dependencies(monkeypatch)
    monkeypatch.setattr(titan_main, "main_menu", lambda _: None)

    with caplog.at_level(logging.INFO):
        titan_main.main()

    assert not any(r.msg == "shutdown_requested" for r in caplog.records)
    assert garmin.stop_calls == 1
    assert weather.stop_calls == 1
    assert telegram.stop_calls == 1
    assert db.closed is True


def test_main_smoke_uses_env_overrides_and_passes_profile_to_context(monkeypatch):
    _garmin, _weather, telegram, _db, _daily_coach, _weekly_planner = _patch_main_dependencies(monkeypatch)

    captured_ctx = {}

    def _capture_main_menu(ctx):
        captured_ctx.update(ctx)

    monkeypatch.setattr(titan_main, "main_menu", _capture_main_menu)
    monkeypatch.setenv("ATHLETE_NAME", "Ada")
    monkeypatch.setenv("ATHLETE_AGE", "41")
    monkeypatch.setenv("ATHLETE_WEIGHT", "62.5")
    monkeypatch.setenv("ATHLETE_HEIGHT", "168")
    monkeypatch.setenv("ATHLETE_MAX_HR", "186")
    monkeypatch.setenv("ATHLETE_THRESHOLD_HR", "164")
    monkeypatch.setenv("TRAINING_PHASE", "PEAK")
    monkeypatch.setenv("TRAINING_GOAL", "MARATHON")

    titan_main.main()

    profile = captured_ctx["athlete_profile"]
    assert profile == {
        "name": "Ada",
        "age": 41,
        "weight_kg": 62.5,
        "height_cm": 168.0,
        "max_hr": 186,
        "threshold_hr": 164,
        "phase": "PEAK",
        "goal": "MARATHON",
    }
    assert {"today", "week", "stats", "recovery", "nutrition", "sync", "activities", "drift", "shoes", "calibration"}.issubset(telegram.commands)


def test_main_smoke_uses_profile_defaults_when_env_missing(monkeypatch):
    _garmin, _weather, _telegram, _db, _daily_coach, _weekly_planner = _patch_main_dependencies(monkeypatch)
    captured_ctx = {}
    monkeypatch.setattr(titan_main, "main_menu", lambda ctx: captured_ctx.update(ctx))

    titan_main.main()

    from titan.core.athlete import UniversalAthleteProfile
    _canonical = UniversalAthleteProfile()
    assert captured_ctx["athlete_profile"] == {
        "name": "Athlete",
        "age": _canonical.age,
        "weight_kg": _canonical.weight_kg,
        "height_cm": float(_canonical.height_cm),
        "max_hr": _canonical.max_hr,
        "threshold_hr": _canonical.threshold_hr,
        "phase": "BUILD",
        "goal": "5K",
    }


def test_main_smoke_invalid_env_value_exits_before_menu(monkeypatch):
    _patch_main_dependencies(monkeypatch)
    called = {"menu": 0}
    monkeypatch.setattr(titan_main, "main_menu", lambda _ctx: called.__setitem__("menu", called["menu"] + 1))
    monkeypatch.setenv("ATHLETE_AGE", "not-an-int")

    with pytest.raises(SystemExit):
        titan_main.main()

    assert called["menu"] == 0


def test_main_schedules_expected_background_tasks(monkeypatch):
    _garmin, _weather, telegram, _db, daily_coach, _weekly_planner = _patch_main_dependencies(monkeypatch)
    monkeypatch.setattr(titan_main, "main_menu", lambda _: None)

    titan_main.main()

    assert len(telegram.scheduled_tasks) == 2
    morning_task, weekly_task = telegram.scheduled_tasks
    assert morning_task["name"] == "Morning Coaching"
    assert morning_task["time_str"] == "07:00"
    morning_task["callback"]()
    assert daily_coach.morning_calls == 1

    assert weekly_task["name"] == "Weekly Plan"
    assert weekly_task["time_str"] == "20:00"
    assert weekly_task["days"] == ["Sunday"]


def test_main_weekly_task_callback_sends_generated_plan(monkeypatch):
    _garmin, _weather, telegram, _db, _daily_coach, weekly_planner = _patch_main_dependencies(monkeypatch)
    captured = {}

    monkeypatch.setattr(titan_main, "main_menu", lambda ctx: captured.setdefault("ctx", ctx))
    monkeypatch.setenv("TRAINING_PHASE", "TAPER")

    titan_main.main()

    weekly_task = next(task for task in telegram.scheduled_tasks if task["name"] == "Weekly Plan")
    weekly_task["callback"]()

    assert weekly_planner.calls
    assert weekly_planner.calls[0]["phase"] == "TAPER"
    assert captured["ctx"]["last_weekly_plan"] == {"status": "ok"}
    assert telegram.sent_weekly_plans == [{"status": "ok"}]


def test_main_runtime_error_still_executes_shutdown_cleanup(monkeypatch):
    garmin, weather, telegram, db, _daily_coach, _weekly_planner = _patch_main_dependencies(monkeypatch)
    monkeypatch.setattr(titan_main, "main_menu", lambda _ctx: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        titan_main.main()

    assert garmin.stop_calls == 1
    assert weather.stop_calls == 1
    assert telegram.stop_calls == 1
    assert db.closed is True


def test_main_has_no_print_calls_for_operational_output_guard():
    source = Path("titan/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    _attach_parents(tree)
    print_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
    ]
    assert _print_call_function_names(print_calls) == ["_print_banner"]


def test_main_emits_operational_startup_and_shutdown_events(monkeypatch, caplog):
    _patch_main_dependencies(monkeypatch)
    monkeypatch.setattr(titan_main, "main_menu", lambda _: None)

    with caplog.at_level(logging.INFO):
        titan_main.main()

    log_messages = {record.msg for record in caplog.records}
    assert "startup_initializing_engines" in log_messages
    assert "background_threads_starting" in log_messages
    assert "scheduled_tasks_configured" in log_messages
    assert "shutdown_started" in log_messages
    assert "shutdown_completed" in log_messages


class _CallbackTelegram:
    def __init__(self):
        self.commands = {}
        self.sent_weekly_plans = []

    def register_command(self, name, callback):
        self.commands[name] = callback

    def send_weekly_plan(self, plan):
        self.sent_weekly_plans.append(plan)


class _RaisingNutrition:
    def analyze_weight_trend(self):
        raise RuntimeError("nutrition unavailable")


class _CallbackDailyCoach:
    def __init__(self, summary):
        self.summary = summary
        self.outcome_tracker = self

    def run_morning_routine(self):
        return None

    def get_calibration_summary(self):
        return self.summary


class _CallbackHRV:
    def get_hrv_summary(self):
        return {"baseline": 52, "trend": "UP", "latest_hrv": 54}


class _CallbackTSB:
    ctl = 81.2
    atl = 69.7

    def calculate_tsb(self):
        return (11.5, "FRESH")


class _CallbackReadiness:
    def analyze_readiness(self, **_kwargs):
        return {"score": 88, "status": "READY", "recommendation": "Train as planned"}


class _CallbackOptTime:
    def calculate_optimal_time(self, **_kwargs):
        return {"recommended_time": "06:30"}


class _CallbackGarmin:
    def sync_all(self):
        return {
            "activities": [{"distance_km": 8.0}],
            "weight": [72.1],
            "hrv": [52],
            "sleep": ["ok"],
        }

    def sync_activities(self, days_back, **kw):
        if days_back == 14:
            return [{"avg_hr": 151, "duration_sec": 3600}]
        return [{"date": "2026-03-01", "distance_km": 10.2, "avg_hr": 149}]


class _CallbackDrift:
    def analyze_cardiac_drift(self, **_kwargs):
        return {"drift_percent": 3.1, "assessment": "STABLE", "lt_zone": "AEROBIC"}


class _CallbackEquipment:
    def recommend_shoe(self, session_type):
        return f"Shoe for {session_type}"


class _CallbackPlanner:
    def generate_weekly_plan(self, athlete_profile, phase):
        return {"phase": phase, "athlete": athlete_profile.get("name", "unknown")}


def _make_callback_context(summary):
    return {
        "daily_coach": _CallbackDailyCoach(summary),
        "weekly_planner": _CallbackPlanner(),
        "athlete_profile": {"name": "Ada", "phase": "PEAK"},
        "hrv_engine": _CallbackHRV(),
        "tsb_engine": _CallbackTSB(),
        "readiness_engine": _CallbackReadiness(),
        "nutrition_optimizer": type(
            "Nutrition",
            (),
            {
                "analyze_weight_trend": lambda self: {"current_weight": 63.2},
                "calculate_daily_nutrition": lambda self, **_kwargs: {
                    "carbs_g": 320,
                    "protein_g": 118,
                    "fat_g": 72,
                    "total_calories": 2650,
                },
            },
        )(),
        "optimal_time_calc": _CallbackOptTime(),
        "garmin": _CallbackGarmin(),
        "drift_engine": _CallbackDrift(),
        "equipment": _CallbackEquipment(),
        "last_garmin_data": {},
        "today_session_type": "TEMPO",
    }


def test_register_telegram_callbacks_success_paths_cover_command_wiring():
    summary = {
        "status": "CALIBRATED",
        "n_decisions": 24,
        "n_with_outcome": 20,
        "completion_rate": 0.8,
        "governance_lock_rate": 0.2,
        "athlete_override_rate": 0.05,
        "avg_rpe_when_completed": 6.2,
        "lock_rate_by_phase": {"BUILD": 0.3},
        "lock_outcome_correlation": {
            "high_fatigue": {"completion_delta_pp": 14, "n_with_lock": 10, "n_without_lock": 8}
        },
        "heuristic_promotion_candidates": [
            {"parameter": "drift_threshold", "completion_delta_pp": 12, "n_with_lock": 9, "n_without_lock": 7, "trigger_lock": "fatigue_lock"}
        ],
        "moderate_promotion_candidates": [
            {
                "parameter": "hrv_floor",
                "completion_delta_pp": 7,
                "n_with_lock": 11,
                "n_without_lock": 10,
                "phase_replication_count": 2,
                "profile_replication_count": 1,
                "trigger_lock": "recovery_lock",
            }
        ],
        "calibration_note": "Stable evidence",
    }
    telegram = _CallbackTelegram()
    ctx = _make_callback_context(summary)

    titan_main._register_telegram_callbacks(telegram, ctx)

    assert set(telegram.commands) == {
        "today",
        "week",
        "stats",
        "recovery",
        "nutrition",
        "sync",
        "activities",
        "drift",
        "shoes",
        "calibration",
    }
    assert "✅" in telegram.commands["today"]()
    assert "✅" in telegram.commands["week"]()
    assert telegram.sent_weekly_plans[-1]["phase"] == "PEAK"
    assert "📊 *STATS*" in telegram.commands["stats"]()
    assert "💊 *RECOVERY*" in telegram.commands["recovery"]()
    assert "🍽 *NUTRITION" in telegram.commands["nutrition"]()
    assert "🔄 *SYNC COMPLETE*" in telegram.commands["sync"]()
    assert "🏃 *RECENT ACTIVITIES*" in telegram.commands["activities"]()
    assert "📉 *CARDIAC DRIFT*" in telegram.commands["drift"]()
    assert "👟 *SHOE RECOMMENDATION*" in telegram.commands["shoes"]()
    assert "• Status: CALIBRATED" in telegram.commands["calibration"]()
    assert "HEURISTIC→MODERATE" in telegram.commands["calibration"]()


def test_register_telegram_callbacks_error_and_empty_branches_return_guard_messages():
    class _RaisingCoach:
        def __init__(self):
            self.outcome_tracker = self

        def run_morning_routine(self):
            raise RuntimeError("coach down")

        def get_calibration_summary(self):
            raise RuntimeError("calibration down")

    class _RaisingPlanner:
        def generate_weekly_plan(self, **_kwargs):
            raise RuntimeError("planner down")

    class _RaisingTSB:
        def calculate_tsb(self):
            raise RuntimeError("tsb down")

    class _RaisingReadiness:
        def analyze_readiness(self, **_kwargs):
            raise RuntimeError("readiness down")

    class _RaisingGarmin:
        def sync_all(self):
            raise RuntimeError("sync failed")

        def sync_activities(self, days_back, **kw):
            return [] if days_back == 14 else (_ for _ in ()).throw(RuntimeError("activities failed"))

    class _RaisingDrift:
        def analyze_cardiac_drift(self, **_kwargs):
            raise RuntimeError("drift down")

    class _RaisingEquipment:
        def recommend_shoe(self, _session_type):
            raise RuntimeError("equipment down")

    telegram = _CallbackTelegram()
    ctx = {
        "daily_coach": _RaisingCoach(),
        "weekly_planner": _RaisingPlanner(),
        "athlete_profile": {},
        "hrv_engine": _CallbackHRV(),
        "tsb_engine": _RaisingTSB(),
        "readiness_engine": _RaisingReadiness(),
        "nutrition_optimizer": _RaisingNutrition(),
        "optimal_time_calc": _CallbackOptTime(),
        "garmin": _RaisingGarmin(),
        "drift_engine": _RaisingDrift(),
        "equipment": _RaisingEquipment(),
        "last_garmin_data": {},
    }

    titan_main._register_telegram_callbacks(telegram, ctx)

    assert telegram.commands["today"]().startswith("❌")
    assert telegram.commands["week"]().startswith("❌")
    assert telegram.commands["stats"]().startswith("❌")
    assert telegram.commands["recovery"]().startswith("❌")
    assert telegram.commands["nutrition"]().startswith("❌")
    assert telegram.commands["sync"]().startswith("❌ Garmin sync failed")
    assert telegram.commands["activities"]().startswith("❌")
    assert telegram.commands["drift"]() == "Δεν υπάρχουν activities για drift analysis."
    assert telegram.commands["shoes"]().startswith("❌")
    assert telegram.commands["calibration"]().startswith("❌")


def test_register_telegram_callbacks_calibration_no_outcomes_and_shoe_missing_manager():
    summary = {"status": "NO_OUTCOMES_YET", "n_decisions": 5, "note": "Need outcomes"}
    telegram = _CallbackTelegram()
    ctx = _make_callback_context(summary)
    ctx["equipment"] = None

    titan_main._register_telegram_callbacks(telegram, ctx)

    calibration = telegram.commands["calibration"]()
    assert "Status: NO_OUTCOMES_YET" in calibration
    assert "Outcomes paired: 0" in calibration
    assert telegram.commands["shoes"]() == "⏳ Equipment manager not configured."


def test_main_shutdown_logs_worker_timeout_before_database_close(monkeypatch, caplog):
    garmin, weather, telegram, db, daily_coach, _weekly_planner = _patch_main_dependencies(monkeypatch)
    close_order = []

    class _AliveThread:
        def is_alive(self):
            return True

        def join(self, timeout):
            close_order.append(f"join_{timeout}")

    daily_coach._routine_thread = _AliveThread()
    monkeypatch.setattr(titan_main, "main_menu", lambda _: None)

    original_close = db.close

    def _tracking_close():
        close_order.append("db_close")
        original_close()

    db.close = _tracking_close

    with caplog.at_level(logging.INFO):
        titan_main.main()

    timeout_record = next(r for r in caplog.records if r.msg == "worker_shutdown_timeout")
    assert timeout_record.worker_name == "DailyCoachRoutine"
    assert close_order == ["join_30", "db_close"]
    assert garmin.stop_calls == 1
    assert weather.stop_calls == 1
    assert telegram.stop_calls == 1


def test_parse_env_number_type_error_uses_same_validation_exit_path(monkeypatch, caplog):
    monkeypatch.setenv("ATHLETE_AGE", "bad")

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
        titan_main._parse_env_number("ATHLETE_AGE", "35", lambda _v: (_ for _ in ()).throw(TypeError("bad type")))

    record = next(r for r in caplog.records if r.msg == "startup_failure")
    assert record.error_class == "TypeError"
    assert "ATHLETE_AGE='bad'" in record.detail


def test_configure_rotating_logging_adds_handler(tmp_path, monkeypatch):
    log_path = tmp_path / "titan.log"
    monkeypatch.setenv("TITAN_LOG_PATH", str(log_path))
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    root.handlers = []

    try:
        titan_main._configure_rotating_logging()
        handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(handlers) == 1
        assert handlers[0].maxBytes == titan_main.LOG_MAX_BYTES
        assert handlers[0].backupCount == titan_main.LOG_BACKUP_COUNT
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = original_handlers


def test_configure_rotating_logging_does_not_duplicate_handler(tmp_path, monkeypatch):
    log_path = tmp_path / "titan.log"
    monkeypatch.setenv("TITAN_LOG_PATH", str(log_path))
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    root.handlers = []

    try:
        titan_main._configure_rotating_logging()
        titan_main._configure_rotating_logging()
        handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(handlers) == 1
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = original_handlers
