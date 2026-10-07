"""INV-16 / RBP-02: unconfigured Telegram trust is a lockout, never open access.

Every inbound handler registered by TitanTelegramBot is invoked from a chat
while no trusted chat id is configured. None may reply, send, run a command
callback, or record an override.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import titan.integrations.telegram_bot as tg


class _FakeBot:
    """Minimal stand-in for telebot.TeleBot that records handlers and outputs."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.handlers: list[tuple[str, dict, object]] = []
        self.replies: list[str] = []
        self.sent: list[tuple] = []
        self.callback_answers: list[tuple] = []

    def message_handler(self, **kwargs):
        def deco(fn):
            self.handlers.append(("message", kwargs, fn))
            return fn

        return deco

    def callback_query_handler(self, **kwargs):
        def deco(fn):
            self.handlers.append(("callback", kwargs, fn))
            return fn

        return deco

    def reply_to(self, _message, text, **_kwargs) -> None:
        self.replies.append(text)

    def send_message(self, *args, **_kwargs) -> None:
        self.sent.append(args)

    def answer_callback_query(self, *args, **_kwargs) -> None:
        self.callback_answers.append(args)


def _make_bot(monkeypatch: pytest.MonkeyPatch, chat_id: str | None) -> tg.TitanTelegramBot:
    monkeypatch.setattr(tg, "get_settings", lambda: SimpleNamespace(TELEGRAM_CHAT_ID=chat_id))
    monkeypatch.setattr(tg, "telebot", SimpleNamespace(TeleBot=_FakeBot), raising=False)
    monkeypatch.setattr(tg, "TELEBOT_AVAILABLE", True)
    monkeypatch.setattr(tg, "_cmd_rate", tg.defaultdict(float))
    bot = tg.TitanTelegramBot(bot_token="test-token", chat_id=None)
    assert isinstance(bot.bot, _FakeBot)
    return bot


def _message(chat_id: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id), text=text)


def _invoke_all_handlers(bot: tg.TitanTelegramBot, chat_id: int) -> None:
    for kind, kwargs, fn in bot.bot.handlers:
        if kind == "callback":
            call = SimpleNamespace(
                id="cb-1",
                data="override:accept:nonce",
                message=_message(chat_id, ""),
            )
            fn(call)
        else:
            command = (kwargs.get("commands") or ["free_text"])[0]
            fn(_message(chat_id, f"/{command} HRV=50"))


def test_unconfigured_trust_refuses_every_handler(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    bot = _make_bot(monkeypatch, chat_id=None)
    callbacks = {name: MagicMock(return_value="data") for name in ("today", "week", "stats", "sync")}
    bot.cmd_callbacks.update(callbacks)
    record_reason = MagicMock()
    monkeypatch.setattr(bot, "process_override_reason", record_reason)
    monkeypatch.setattr(bot, "process_override_callback", record_reason)

    assert len(bot.bot.handlers) >= 10  # every command plus the override paths

    with caplog.at_level(logging.CRITICAL, logger="titan.integrations.telegram_bot"):
        _invoke_all_handlers(bot, chat_id=4242)

    assert bot.bot.replies == []
    assert bot.bot.sent == []
    assert all(len(args) == 1 for args in bot.bot.callback_answers)  # bare ack, no content
    for cb in callbacks.values():
        cb.assert_not_called()
    record_reason.assert_not_called()
    assert bot.chat_id is None  # /start must not auto-capture an unconfigured chat
    assert "no_trusted_chat_configured" in caplog.text


def test_configured_trust_still_serves_trusted_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = _make_bot(monkeypatch, chat_id="4242")
    bot.cmd_callbacks["today"] = MagicMock(return_value="today's plan")

    today = next(fn for kind, kw, fn in bot.bot.handlers if kw.get("commands") == ["today"])
    today(_message(4242, "/today"))

    assert bot.bot.replies == ["today's plan"]


def test_configured_trust_refuses_other_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = _make_bot(monkeypatch, chat_id="4242")
    bot.cmd_callbacks["today"] = MagicMock(return_value="today's plan")

    _invoke_all_handlers(bot, chat_id=1111)

    assert bot.bot.replies == []
    assert bot.bot.sent == []
    bot.cmd_callbacks["today"].assert_not_called()
