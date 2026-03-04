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
