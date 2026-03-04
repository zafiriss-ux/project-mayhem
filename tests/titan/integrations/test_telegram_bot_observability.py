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
