#!/usr/bin/env python3
"""
Unit tests for TitanTelegramBot.

Tests message formatting, command dispatch, scheduling, alert emoji mapping,
and fallback behaviour when the telebot library is absent or the token is empty.

Run with:
    pytest test_telegram_bot.py -v
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── env stub ─────────────────────────────────────────────────────────────────
os.environ.setdefault("GARMIN_EMAIL",        "test@example.com")
os.environ.setdefault("GARMIN_PASSWORD",     "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN",  "")   # empty → no real polling
os.environ.setdefault("TELEGRAM_CHAT_ID",    "12345")
os.environ.setdefault("WEATHER_API_KEY",     "test")
os.environ.setdefault("WEATHER_LOCATION",    "Athens,GR")

sys.path.insert(0, str(Path(__file__).parent))

from titan.integrations.telegram_bot import TitanTelegramBot


# ════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def bot():
    """Bot with empty token → fallback (log-only) mode, chat_id=12345."""
    return TitanTelegramBot(bot_token="", chat_id="12345")


@pytest.fixture
def _weekly_plan():
    """Minimal weekly plan dict for send_weekly_plan() tests."""
    return {
        "week_start":    "2026-02-24",
        "phase":         "BUILD",
        "total_km":      60,
        "quality_count": 2,
        "easy_count":    3,
        "rest_count":    2,
        "lactate_threshold": 165,
        "hrv_baseline":  58.0,
        "tsb_status":    "🎯 RACE FORM",
        "daily_sessions": [
            {
                "day":          "Monday",
                "session_type": "EASY",
                "distance_km":  8,
                "details":      "Recovery run",
                "optimal_time": "07:00",
            }
        ],
        "motivation": "Train smart, race fast!",
    }


@pytest.fixture
def _coaching_data():
    """Minimal coaching data dict for send_daily_coaching() tests."""
    return {
        "session_type":   "TEMPO",
        "duration":       "12 km",
        "optimal_time":   "07:30",
        "dew_point":      12,
        "conditions":     "GOOD",
        "hrv_status":     "STABLE",
        "sleep_quality":  80,
        "readiness_score": 75,
        "nutrition_plan": "250g carbs, 120g protein",
        "shoe":           "Daily trainer",
    }


@pytest.fixture
def _run_data():
    """Post-run analysis dict."""
    return {
        "distance_km":   10,
        "duration":      "50:00",
        "avg_pace":      "5:00",
        "avg_hr":        145,
        "hr_drift":      2.5,
        "efficiency":    "GOOD",
        "training_load": 55,
        "next_steps":    "Rest and refuel",
    }


# ════════════════════════════════════════════════════════════════════════════
# 1. INITIALISATION
# ════════════════════════════════════════════════════════════════════════════

class TestTelegramBotInit:

    def test_empty_token_leaves_bot_none(self, bot):
        assert bot.bot is None

    def test_chat_id_parsed_as_int_from_string(self):
        b = TitanTelegramBot(bot_token="", chat_id="99999")
        assert b.chat_id == 99999

    def test_invalid_chat_id_kept_as_string(self):
        b = TitanTelegramBot(bot_token="", chat_id="not_a_number")
        assert isinstance(b.chat_id, str)

    def test_is_running_false_on_init(self, bot):
        assert bot.is_running is False

    def test_message_history_empty_on_init(self, bot):
        assert bot.message_history == []

    def test_cmd_callbacks_empty_on_init(self, bot):
        assert bot.cmd_callbacks == {}

    def test_scheduled_tasks_empty_on_init(self, bot):
        assert bot.scheduled_tasks == []

    def test_stop_flag_false_on_init(self, bot):
        assert bot._stop is False
        assert bot._stop_event.is_set() is False


# ════════════════════════════════════════════════════════════════════════════
# 2. send_message — fallback (no telebot / no token) mode
# ════════════════════════════════════════════════════════════════════════════

class TestSendMessage:

    def test_returns_true_with_chat_id(self, bot):
        assert bot.send_message("Hello TITAN") is True

    def test_returns_false_without_chat_id(self, monkeypatch):
        """Bot with no chat_id (and env var cleared) must return False."""
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        b = TitanTelegramBot(bot_token="", chat_id="")
        assert b.send_message("Hello") is False

    def test_logs_to_stdout_in_fallback(self, bot, capsys):
        bot.send_message("Test payload")
        out = capsys.readouterr().out
        # Fallback prints something — either "[Telegram]" prefix or the text
        assert len(out) > 0


# ════════════════════════════════════════════════════════════════════════════
# 3. Message formatters
# ════════════════════════════════════════════════════════════════════════════

class TestMessageFormatters:

    def test_send_daily_coaching_returns_bool(self, bot, _coaching_data):
        assert isinstance(bot.send_daily_coaching(_coaching_data), bool)

    def test_send_daily_coaching_special_note(self, bot, _coaching_data):
        """special_note field must be included when present."""
        _coaching_data["special_note"] = "Recovery day — take it easy!"
        # Intercept send_message to inspect the text
        captured = []
        bot.send_message = lambda text, **kw: captured.append(text) or True
        bot.send_daily_coaching(_coaching_data)
        assert any("Recovery day" in t for t in captured)

    def test_send_weekly_plan_returns_bool(self, bot, _weekly_plan):
        assert isinstance(bot.send_weekly_plan(_weekly_plan), bool)

    def test_send_weekly_plan_includes_session_days(self, bot, _weekly_plan):
        captured = []
        bot.send_message = lambda text, **kw: captured.append(text) or True
        bot.send_weekly_plan(_weekly_plan)
        assert any("Monday" in t for t in captured)

    def test_send_weekly_plan_includes_optimal_time(self, bot, _weekly_plan):
        captured = []
        bot.send_message = lambda text, **kw: captured.append(text) or True
        bot.send_weekly_plan(_weekly_plan)
        assert any("07:00" in t for t in captured)

    def test_send_post_run_analysis_returns_bool(self, bot, _run_data):
        assert isinstance(bot.send_post_run_analysis(_run_data), bool)

    def test_send_alert_returns_bool(self, bot):
        assert isinstance(bot.send_alert("Test", "Detail", level="warning"), bool)

    @pytest.mark.parametrize("level,emoji", [
        ("critical", "🛑"),
        ("warning",  "⚠️"),
        ("info",     "ℹ️"),
        ("ok",       "✅"),
    ])
    def test_send_alert_uses_correct_emoji(self, bot, level, emoji):
        captured = []
        bot.send_message = lambda text, **kw: captured.append(text) or True
        bot.send_alert("Title", "Body", level=level)
        assert any(emoji in t for t in captured), (
            f"Expected emoji {emoji!r} for level {level!r} not found"
        )

    def test_send_alert_unknown_level_uses_info_emoji(self, bot):
        captured = []
        bot.send_message = lambda text, **kw: captured.append(text) or True
        bot.send_alert("T", "B", level="unknown_level")
        assert any("ℹ️" in t for t in captured)


    def test_send_daily_coaching_sleep_scale_is_100(self, bot, _coaching_data):
        captured = []
        bot.send_message = lambda text, **kw: captured.append(text) or True
        bot.send_daily_coaching(_coaching_data)
        assert any("Sleep: 80/100" in t for t in captured)

    def test_send_daily_coaching_includes_session_type(self, bot, _coaching_data):
        captured = []
        bot.send_message = lambda text, **kw: captured.append(text) or True
        bot.send_daily_coaching(_coaching_data)
        assert any("TEMPO" in t for t in captured)

    def test_send_post_run_includes_distance(self, bot, _run_data):
        captured = []
        bot.send_message = lambda text, **kw: captured.append(text) or True
        bot.send_post_run_analysis(_run_data)
        assert any("10" in t for t in captured)


# ════════════════════════════════════════════════════════════════════════════
# 4. Command callback dispatch
# ════════════════════════════════════════════════════════════════════════════

class TestCommandCallbacks:

    def test_register_command_stores_callback(self, bot):
        cb = MagicMock(return_value="pong")
        bot.register_command("ping", cb)
        assert "ping" in bot.cmd_callbacks
        assert bot.cmd_callbacks["ping"]() == "pong"

    def test_overwrite_command_callback(self, bot):
        bot.register_command("today", lambda: "v1")
        bot.register_command("today", lambda: "v2")
        assert bot.cmd_callbacks["today"]() == "v2"

    def test_multiple_commands_registered(self, bot):
        for cmd in ("today", "week", "stats", "recovery", "nutrition"):
            bot.register_command(cmd, lambda: cmd)
        assert set(bot.cmd_callbacks.keys()) >= {"today", "week", "stats"}


# ════════════════════════════════════════════════════════════════════════════
# 5. Scheduler
# ════════════════════════════════════════════════════════════════════════════

class TestScheduler:

    def test_schedule_task_adds_entry(self, bot):
        bot.schedule_task("morning", "07:00", lambda: None)
        assert len(bot.scheduled_tasks) == 1

    def test_schedule_task_defaults_all_seven_days(self, bot):
        bot.schedule_task("morning", "07:00", lambda: None)
        assert len(bot.scheduled_tasks[0]["days"]) == 7

    def test_schedule_task_custom_days(self, bot):
        bot.schedule_task("sunday_plan", "20:00", lambda: None, days=["Sunday"])
        assert bot.scheduled_tasks[0]["days"] == ["Sunday"]

    def test_schedule_task_stores_name_and_time(self, bot):
        bot.schedule_task("my_task", "09:30", lambda: None)
        task = bot.scheduled_tasks[0]
        assert task["name"] == "my_task"
        assert task["time"] == "09:30"

    def test_multiple_tasks_accumulated(self, bot):
        for i in range(3):
            bot.schedule_task(f"task_{i}", f"0{7 + i}:00", lambda: None)
        assert len(bot.scheduled_tasks) == 3

    def test_task_callback_is_callable(self, bot):
        cb = MagicMock()
        bot.schedule_task("cb_test", "08:00", cb)
        bot.scheduled_tasks[0]["callback"]()
        cb.assert_called_once()


# ════════════════════════════════════════════════════════════════════════════
# 6. Start / Stop lifecycle
# ════════════════════════════════════════════════════════════════════════════

class TestStartStop:

    def test_start_sets_is_running_true(self, bot):
        bot.start_bot()
        assert bot.is_running is True
        bot.stop_bot()

    def test_stop_sets_is_running_false(self, bot):
        bot.start_bot()
        bot.stop_bot()
        assert bot.is_running is False
        assert bot._stop_event.is_set() is True

    def test_double_start_is_idempotent(self, bot):
        """Calling start_bot() twice on the same instance must not raise."""
        bot.start_bot()
        first_thread = bot._sched_thread
        bot.start_bot()  # second call → guarded by is_running flag
        # The scheduler thread must be the same object (not replaced)
        assert bot._sched_thread is first_thread
        bot.stop_bot()

    def test_stop_before_start_does_not_raise(self, bot):
        bot.stop_bot()   # no-op; must not raise
