import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import titan.integrations.telegram_bot as telegram_bot
from titan.integrations.telegram_bot import TitanTelegramBot


class _FakeTeleBot:
    def __init__(self):
        self.handlers = {}
        self.callback_handlers = []
        self.replies = []
        self.sent_messages = []
        self.callback_answers = []

    def message_handler(self, commands=None, **kwargs):
        def _decorator(fn):
            if commands:
                for command in commands:
                    self.handlers[command] = fn
            else:
                self.handlers[f"func_{len(self.handlers)}"] = fn
            return fn

        return _decorator

    def reply_to(self, message, text):
        self.replies.append((message, text))

    def callback_query_handler(self, func):
        def _decorator(handler):
            self.callback_handlers.append((func, handler))
            return handler

        return _decorator

    def answer_callback_query(self, callback_id, text):
        self.callback_answers.append((callback_id, text))

    def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent_messages.append((chat_id, text, parse_mode, reply_markup))


def test_send_message_without_bot_emits_send_fail_event(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))

    bot = TitanTelegramBot(bot_token="", chat_id=123)

    assert bot.send_message("hello") is True
    assert any(
        action == "failure"
        and fields.get("failure_class") == telegram_bot.SEND_FAIL
        and fields.get("reason") == "fallback_console_only"
        for action, fields in events
    )


def test_send_message_without_chat_id_returns_false_and_emits_missing_chat_id_events(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")

    bot = TitanTelegramBot(bot_token="", chat_id=None)

    assert bot.send_message("hello") is False
    assert any(action == "slo_alert" and fields.get("slo_key") == "telegram_delivery_missing_chat_id" for action, fields in events)
    assert any(
        action == "failure"
        and fields.get("failure_class") == telegram_bot.SEND_FAIL
        and fields.get("reason") == "missing_chat_id"
        for action, fields in events
    )


def test_send_message_telegram_api_success_records_history(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.bot = MagicMock()
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)

    assert bot.send_message("hello", parse_mode="HTML") is True
    bot.bot.send_message.assert_called_once_with(123, "hello", parse_mode="HTML")
    assert bot.message_history[-1]["delivery_mode"] == "telegram_api"


def test_send_message_telegram_api_error_returns_false(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))

    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.bot = MagicMock()
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    bot.bot.send_message.side_effect = RuntimeError("send failed")

    assert bot.send_message("hello") is False
    assert any(action == "slo_alert" and fields.get("slo_key") == "telegram_delivery_failed" for action, fields in events)
    assert any(
        action == "failure"
        and fields.get("failure_class") == telegram_bot.SEND_FAIL
        and fields.get("error_class") == "RuntimeError"
        for action, fields in events
    )


def test_send_message_fallback_logs_metadata_without_message_content(monkeypatch, caplog):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))

    bot = TitanTelegramBot(bot_token="", chat_id=123)
    secret_message = "SECRET123"

    with caplog.at_level("INFO"):
        assert bot.send_message(secret_message) is True

    fallback_record = next(r for r in caplog.records if r.msg == "telegram_fallback_delivery_preview")
    assert fallback_record.message_length == len(secret_message)
    assert fallback_record.delivery_mode == "fallback"
    assert fallback_record.reason == "fallback_console_only"
    assert "SECRET123" not in caplog.text
    assert not hasattr(fallback_record, "message_preview")

    fallback_event = next(
        fields
        for action, fields in events
        if action == "failure" and fields.get("reason") == "fallback_console_only"
    )
    assert "SECRET123" not in str(fallback_event)


def test_start_bot_without_polling_backend_emits_poll_fail_event(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))

    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.start_bot()
    bot.stop_bot()

    assert any(
        action == "failure"
        and fields.get("failure_class") == telegram_bot.POLL_FAIL
        and fields.get("reason") == "polling_unavailable"
        for action, fields in events
    )


def test_stop_bot_stop_polling_exception_emits_poll_fail_event(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))

    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.bot = MagicMock()
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    bot.bot.stop_polling.side_effect = RuntimeError("stop failed")

    bot.stop_bot()

    assert any(
        action == "failure"
        and fields.get("failure_class") == telegram_bot.POLL_FAIL
        and fields.get("subsystem") == "stop_bot"
        and fields.get("error_class") == "RuntimeError"
        for action, fields in events
    )


def test_init_happy_path_builds_bot(monkeypatch):
    class _DummyTeleBot:
        def __init__(self, token, parse_mode=None):
            self.token = token
            self.parse_mode = parse_mode

        def message_handler(self, *args, **kwargs):
            def _decorator(fn):
                return fn

            return _decorator

    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    monkeypatch.setattr(telegram_bot, "telebot", type("_TelebotMod", (), {"TeleBot": _DummyTeleBot}), raising=False)

    bot = TitanTelegramBot(bot_token="token-1", chat_id=123)

    assert bot.bot is not None


def test_init_failure_logs_structured_startup_event(monkeypatch, caplog):
    class _FailingTeleBot:
        def __init__(self, token, parse_mode=None):
            raise RuntimeError("invalid token")

    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    monkeypatch.setattr(telegram_bot, "telebot", type("_TelebotMod", (), {"TeleBot": _FailingTeleBot}), raising=False)

    with caplog.at_level("ERROR"):
        bot = TitanTelegramBot(bot_token="token-1", chat_id=123)

    assert bot.bot is None
    record = next(r for r in caplog.records if r.msg == "startup_failure")
    assert record.component == "telegram_bot_init"
    assert record.error_class == "RuntimeError"
    assert record.detail == "invalid token"


def test_init_uses_redacted_secret_container_without_duplicate_aliases():
    bot = TitanTelegramBot(bot_token="token-1", chat_id=123)

    assert bot.bot_token.reveal() == "token-1"
    assert str(bot.bot_token) == "***"
    assert repr(bot.bot_token) == "'***'"
    assert not hasattr(bot, "_bot_token_secret")


def test_init_missing_token_fails_safely(monkeypatch):
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    bot = TitanTelegramBot(bot_token="", chat_id=123)

    assert bot.bot is None


def test_register_handlers_no_bot_is_noop():
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.bot = None
    bot._register_handlers()


def test_command_handlers_route_to_callbacks_and_fallbacks():
    fake_bot = _FakeTeleBot()
    bot = TitanTelegramBot(bot_token="", chat_id=999)
    bot.bot = fake_bot
    bot._register_handlers()

    message = type("_Message", (), {"chat": type("_Chat", (), {"id": 321})()})()

    callback_matrix = {
        "today": ("⏳ Calculating...", "⏳ Daily coach not ready yet."),
        "week": ("⏳ Generating plan...", "⏳ Weekly planner not ready yet."),
        "stats": ("⏳ Loading stats...", "⏳ Stats not ready yet."),
        "recovery": ("⏳ Checking recovery...", "⏳ Recovery engine not ready."),
        "nutrition": ("⏳ Building nutrition plan...", "⏳ Nutrition optimizer not ready."),
        "activities": ("No activities found.", "⏳ Activity data not ready."),
        "drift": ("No drift data yet.", "⏳ Drift analysis not ready."),
        "shoes": ("No shoe data configured.", "⏳ Equipment manager not ready."),
        "calibration": ("⏳ No calibration data yet.", "⏳ Outcome tracker not ready."),
    }

    for command, (empty_fallback, no_callback_fallback) in callback_matrix.items():
        fake_bot.replies.clear()
        bot.cmd_callbacks.pop(command, None)
        fake_bot.handlers[command](message)
        assert fake_bot.replies[-1][1] == no_callback_fallback

        fake_bot.replies.clear()
        bot.cmd_callbacks[command] = lambda: ""
        fake_bot.handlers[command](message)
        assert fake_bot.replies[-1][1] == empty_fallback

        fake_bot.replies.clear()
        bot.cmd_callbacks[command] = lambda: "READY"
        fake_bot.handlers[command](message)
        assert fake_bot.replies[-1][1] == "READY"

    fake_bot.replies.clear()
    bot.cmd_callbacks.pop("sync", None)
    fake_bot.handlers["sync"](message)
    assert fake_bot.replies[0][1] == "🔄 Starting Garmin sync..."
    assert fake_bot.replies[1][1] == "⏳ Sync not available yet."

    fake_bot.replies.clear()
    bot.cmd_callbacks["sync"] = lambda: ""
    fake_bot.handlers["sync"](message)
    assert fake_bot.replies[0][1] == "🔄 Starting Garmin sync..."
    assert fake_bot.replies[1][1] == "✅ Sync complete."

    fake_bot.replies.clear()
    bot.cmd_callbacks["sync"] = lambda: "SYNCED"
    fake_bot.handlers["sync"](message)
    assert fake_bot.replies[1][1] == "SYNCED"

    fake_bot.handlers["start"](message)
    assert bot.chat_id == 321
    assert "Available Commands" in fake_bot.replies[-1][1]


def test_register_command_overwrites_existing_callback():
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.register_command("today", lambda: "A")
    bot.register_command("today", lambda: "B")

    assert bot.cmd_callbacks["today"]() == "B"


def test_scheduler_worker_continues_when_stop_event_not_set(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    calls = []

    class _Now:
        second = 0

        def strftime(self, value):
            if value == "%H:%M":
                return "07:00"
            if value == "%A":
                return "Monday"
            raise AssertionError("unexpected format")

    bot.scheduled_tasks = [
        {"name": "n", "time": "07:00", "days": ["Monday"], "callback": lambda: calls.append("run")}
    ]

    monkeypatch.setattr(telegram_bot, "datetime", type("_D", (), {"now": staticmethod(lambda: _Now())}))
    monkeypatch.setattr(telegram_bot.time, "time", lambda: 100.0)

    wait_calls = {"count": 0}

    def _wait(timeout):
        wait_calls["count"] += 1
        if wait_calls["count"] == 2:
            bot._stop_event.set()
        return False

    monkeypatch.setattr(bot._stop_event, "wait", _wait)

    bot._scheduler_worker()

    assert len(calls) >= 2


def test_stop_bot_sets_event_and_joins_threads():
    bot = TitanTelegramBot(bot_token="", chat_id=123)

    bot._sched_thread = MagicMock()
    bot._sched_thread.is_alive.return_value = True
    bot._poll_thread = MagicMock()
    bot._poll_thread.is_alive.return_value = True

    bot.stop_bot()

    assert bot._stop_event.is_set()
    bot._sched_thread.join.assert_called_once_with(timeout=5)
    bot._poll_thread.join.assert_called_once_with(timeout=5)


def test_start_bot_when_already_running_returns_without_spawning_threads(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.is_running = True
    thread_ctor = MagicMock()
    monkeypatch.setattr(telegram_bot.threading, "Thread", thread_ctor)

    bot.start_bot()

    thread_ctor.assert_not_called()


def test_start_bot_with_polling_backend_starts_both_threads(monkeypatch):
    created_threads = []

    class _FakeThread:
        def __init__(self, target, daemon, name):
            self.target = target
            self.daemon = daemon
            self.name = name
            self.started = False
            created_threads.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(telegram_bot.threading, "Thread", _FakeThread)
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.bot = MagicMock()

    bot.start_bot()

    assert [t.name for t in created_threads] == ["TelegramScheduler", "TelegramPoller"]
    assert all(t.started for t in created_threads)


def test_stop_bot_emits_shutdown_timeout_for_scheduler_thread(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))

    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot._sched_thread = MagicMock()
    bot._sched_thread.is_alive.return_value = True

    bot.stop_bot()

    assert any(
        action == "worker_shutdown_timeout"
        and fields.get("level") == "error"
        and fields.get("worker_name") == "Scheduler"
        and fields.get("timeout_seconds") == 5
        and fields.get("still_alive") is True
        for action, fields in events
    )


def test_stop_bot_emits_shutdown_timeout_for_poll_thread(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))

    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot._poll_thread = MagicMock()
    bot._poll_thread.is_alive.return_value = True

    bot.stop_bot()

    assert any(
        action == "worker_shutdown_timeout"
        and fields.get("level") == "error"
        and fields.get("worker_name") == "Polling"
        and fields.get("timeout_seconds") == 5
        and fields.get("still_alive") is True
        for action, fields in events
    )


def test_poll_worker_reports_poll_fail_and_waits_before_retry(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.bot = MagicMock()
    bot.bot.infinity_polling.side_effect = RuntimeError("network")

    calls = {"count": 0}

    def _wait(timeout):
        calls["count"] += 1
        bot._stop_event.set()
        return False

    monkeypatch.setattr(bot._stop_event, "wait", _wait)

    bot._poll_worker()

    assert calls["count"] == 1
    assert any(
        action == "failure"
        and fields.get("failure_class") == telegram_bot.POLL_FAIL
        and fields.get("subsystem") == "poll_worker"
        for action, fields in events
    )


def test_poll_worker_ignores_exception_once_stop_event_is_set(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.bot = MagicMock()

    def _boom(*args, **kwargs):
        bot._stop_event.set()
        raise RuntimeError("stopped")

    bot.bot.infinity_polling.side_effect = _boom

    bot._poll_worker()

    assert events == []

def test_scheduler_worker_allows_concurrent_append_without_runtime_error(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    errors: list[Exception] = []

    class _CheckedTasks(list):
        def append(self, item):
            if not bot._tasks_lock.locked():
                raise RuntimeError("append_without_lock")
            super().append(item)

        def __iter__(self):
            if not bot._tasks_lock.locked():
                raise RuntimeError("iterate_without_lock")
            return super().__iter__()

    bot.scheduled_tasks = _CheckedTasks()
    bot.schedule_task("seed", "07:00", lambda: None, days=["Monday"])

    class _Now:
        second = 0

        def strftime(self, value):
            if value == "%H:%M":
                return "07:00"
            if value == "%A":
                return "Monday"
            raise AssertionError("unexpected format")

    monkeypatch.setattr(telegram_bot, "datetime", type("_D", (), {"now": staticmethod(lambda: _Now())}))
    monkeypatch.setattr(telegram_bot.time, "time", lambda: 100.0)

    wait_calls = {"count": 0}

    def _wait(timeout):
        wait_calls["count"] += 1
        if wait_calls["count"] >= 10:
            bot._stop_event.set()
        return False

    monkeypatch.setattr(bot._stop_event, "wait", _wait)

    def _run_worker():
        try:
            bot._scheduler_worker()
        except Exception as exc:  # pragma: no cover - assertion path
            errors.append(exc)
            bot._stop_event.set()

    def _append_tasks():
        try:
            for idx in range(25):
                bot.schedule_task(f"n-{idx}", "07:00", lambda: None, days=["Monday"])
                time.sleep(0.001)
        except Exception as exc:  # pragma: no cover - assertion path
            errors.append(exc)
            bot._stop_event.set()

    worker = threading.Thread(target=_run_worker, daemon=True)
    appender = threading.Thread(target=_append_tasks, daemon=True)

    worker.start()
    appender.start()
    appender.join(timeout=2)
    bot._stop_event.set()
    worker.join(timeout=2)

    assert not errors


def test_scheduler_worker_emits_drift_and_callback_error(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))
    bot = TitanTelegramBot(bot_token="", chat_id=123)

    class _Now:
        def __init__(self, second):
            self.second = second

        def strftime(self, value):
            if value == "%H:%M":
                return "07:00"
            if value == "%A":
                return "Monday"
            raise AssertionError("unexpected format")

    now_values = iter([_Now(0), _Now(0)])
    monkeypatch.setattr(telegram_bot, "datetime", type("_D", (), {"now": staticmethod(lambda: next(now_values))}))
    time_values = iter([100.0, 170.0])

    def _time_now():
        return next(time_values, 170.0)

    monkeypatch.setattr(telegram_bot.time, "time", _time_now)

    bot.scheduled_tasks = [
        {
            "name": "crash",
            "time": "07:00",
            "days": ["Monday"],
            "callback": lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        }
    ]

    waits = {"count": 0}

    def _wait(timeout):
        waits["count"] += 1
        if waits["count"] >= 2:
            bot._stop_event.set()
        return False

    monkeypatch.setattr(bot._stop_event, "wait", _wait)

    bot._scheduler_worker()

    assert any(
        action == "failure" and fields.get("failure_class") == telegram_bot.SCHEDULER_DRIFT
        for action, fields in events
    )
    assert any(
        action == "failure"
        and fields.get("failure_class") == telegram_bot.CALLBACK_ERROR
        and fields.get("task_name") == "crash"
        for action, fields in events
    )


def test_schedule_task_emits_scheduler_task_added_event(monkeypatch):
    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **fields: events.append((action, fields)))

    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.schedule_task("morning", "07:00", lambda: None, days=["Monday"], source="unit_test")

    assert any(
        action == "scheduler_task_added"
        and fields.get("task_name") == "morning"
        and fields.get("scheduled_time") == "07:00"
        and fields.get("source") == "unit_test"
        for action, fields in events
    )


def test_send_weekly_plan_formats_and_delegates_to_send_message(monkeypatch):
    captured = {"text": None}
    bot = TitanTelegramBot(bot_token="", chat_id=123)

    def _send_message(text, parse_mode="Markdown"):
        captured["text"] = text
        return True

    monkeypatch.setattr(bot, "send_message", _send_message)

    result = bot.send_weekly_plan(
        {
            "phase": "BUILD",
            "total_km": 62,
            "quality_count": 2,
            "easy_count": 3,
            "rest_count": 1,
            "lactate_threshold": 167,
            "hrv_baseline": 61,
            "tsb_status": "BALANCED",
            "daily_sessions": [
                {
                    "day": "Monday",
                    "session_type": "EASY",
                    "distance_km": 10,
                    "details": "Easy aerobic",
                    "optimal_time": "06:00",
                }
            ],
            "motivation": "Keep moving",
        }
    )

    assert result is True
    assert "*WEEKLY TRAINING PLAN*" in captured["text"]
    assert "Best time: 06:00" in captured["text"]


def test_send_alert_uses_info_default_for_unknown_level(monkeypatch):
    captured = {"text": None}
    bot = TitanTelegramBot(bot_token="", chat_id=123)

    def _send_message(text, parse_mode="Markdown"):
        captured["text"] = text
        return True

    monkeypatch.setattr(bot, "send_message", _send_message)

    result = bot.send_alert("Title", "Body", level="unsupported")

    assert result is True
    assert captured["text"].startswith("ℹ️ *Title*")

def test_telegram_bot_has_no_print_calls():
    source = Path("titan/integrations/telegram_bot.py").read_text(encoding="utf-8")
    assert "print(" not in source


def test_send_structured_alert_happy_path_first_critical_delivery(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    calls = []
    monkeypatch.setattr(bot, "send_alert", lambda title, message, level="warning": calls.append((title, message, level)) or True)

    assert bot.send_structured_alert("garmin_data_stale", "GARMIN_DATA_STALE", "stale data") is True
    assert calls == [("CRITICAL", "stale data", "critical")]


def test_send_structured_alert_boundary_deduplicates_within_window(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    calls = []
    monkeypatch.setattr(bot, "send_alert", lambda title, message, level="warning": calls.append((title, message, level)) or True)

    assert bot.send_structured_alert("garmin_data_stale", "GARMIN_DATA_STALE", "stale data") is True
    assert bot.send_structured_alert("garmin_data_stale", "GARMIN_DATA_STALE", "stale data") is False
    assert calls == [("CRITICAL", "stale data", "critical")]


def test_send_structured_alert_sends_summary_after_persist_window(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    calls = []
    monkeypatch.setattr(bot, "send_alert", lambda title, message, level="warning": calls.append((title, message, level)) or True)

    assert bot.send_structured_alert("garmin_data_stale", "GARMIN_DATA_STALE", "stale data") is True
    snapshot = bot._alert_history[("garmin_data_stale", "GARMIN_DATA_STALE")]
    snapshot["first_seen"] = snapshot["first_seen"] - telegram_bot.timedelta(hours=73)
    snapshot["last_sent"] = snapshot["last_sent"] - telegram_bot.timedelta(hours=21)

    assert bot.send_structured_alert("garmin_data_stale", "GARMIN_DATA_STALE", "stale data") is True
    assert calls[-1][0] == "CRITICAL SUMMARY"
    assert calls[-1][2] == "warning"



def test_send_governance_decision_falls_back_when_polling_backend_missing():
    bot = TitanTelegramBot(bot_token="", chat_id=123)

    assert bot.send_governance_decision(
        text="Hard stop",
        decision_id="d-1",
        decision_type="HARD_STOP_SAFETY_GATES",
        athlete_id="ATH_1",
    ) is True
    assert bot._pending_override_prompts[123]["decision_id"] == "d-1"


def test_process_override_callback_and_reason_records_signal(monkeypatch):
    class _DB:
        def __init__(self):
            self.rows = []

        def record_override_signal(self, **kwargs):
            self.rows.append(kwargs)

    db = _DB()
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot.register_override_callback("db_provider", lambda: db)
    bot._pending_override_prompts[123] = {
        "decision_id": "d-2",
        "athlete_id": "ATH_2",
        "decision_type": "VO2_ELIGIBILITY_GATE",
        "created_at": "2026-03-07T09:00:00+00:00",
    }

    assert "required" in bot.process_override_callback(123, "override:request")
    assert bot.process_override_reason(123, "Need to adjust due to artifact") == "✅ Override recorded."
    assert db.rows[0]["decision_id"] == "d-2"


def test_process_override_reason_rejects_empty_reason():
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    bot._pending_override_prompts[123] = {
        "decision_id": "d-3",
        "athlete_id": "ATH_3",
        "decision_type": "VO2_ELIGIBILITY_GATE",
        "created_at": "2026-03-07T09:00:00+00:00",
        "awaiting_reason": "1",
    }

    assert bot.process_override_reason(123, "   ") == "⚠️ Override reason is required."


def test_start_bot_removes_webhook_before_polling(monkeypatch):
    """start_bot() calls remove_webhook() to prevent Telegram 409 Conflict."""
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    fake_bot = MagicMock()
    bot.bot = fake_bot

    # Prevent threads from actually starting
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)

    bot.start_bot()

    fake_bot.remove_webhook.assert_called_once()


def test_start_bot_handles_webhook_removal_failure(monkeypatch):
    """start_bot() survives remove_webhook() failure and still starts polling."""
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    fake_bot = MagicMock()
    fake_bot.remove_webhook.side_effect = RuntimeError("network error")
    bot.bot = fake_bot

    monkeypatch.setattr(threading.Thread, "start", lambda self: None)

    events = []
    monkeypatch.setattr(telegram_bot, "_telegram_event", lambda action, **kw: events.append(action))

    bot.start_bot()

    assert "webhook_removal_failed" in events
    assert bot.is_running


def test_start_bot_prevents_double_polling(monkeypatch):
    """Calling start_bot() twice does not start a second polling thread."""
    monkeypatch.setattr(telegram_bot, "TELEBOT_AVAILABLE", True)
    bot = TitanTelegramBot(bot_token="", chat_id=123)
    fake_bot = MagicMock()
    bot.bot = fake_bot

    thread_starts = {"count": 0}

    def counting_start(self):
        thread_starts["count"] += 1

    monkeypatch.setattr(threading.Thread, "start", counting_start)

    bot.start_bot()
    first_count = thread_starts["count"]
    bot.start_bot()  # second call — should be no-op
    assert thread_starts["count"] == first_count, "Second start_bot() must not spawn extra threads"
