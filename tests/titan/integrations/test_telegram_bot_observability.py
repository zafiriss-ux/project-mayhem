import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import titan.integrations.telegram_bot as telegram_bot
from titan.integrations.telegram_bot import TitanTelegramBot


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
