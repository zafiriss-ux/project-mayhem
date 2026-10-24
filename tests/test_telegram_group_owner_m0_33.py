"""M0-33: in a group chat only the owner's own messages are owner commands.

The owner's TELEGRAM_CHAT_ID may be a group (a negative id). Every member writes in it, so
the chat alone does not say who sent a command: the sender must also be
TELEGRAM_OWNER_USER_ID. Without that setting no group message is a command (fail closed,
INV-16). A private chat is unchanged. Synthetic ids only.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from titan.integrations.telegram_bot import TitanTelegramBot, _cmd_rate

GROUP = -100123
OWNER_USER, MEMBER_USER = 4242, 5151
PRIVATE_OWNER_CHAT = 4242


class _FakeTeleBot:
    def __init__(self) -> None:
        self.handlers: dict = {}
        self.callback = None
        self.reason_handler = None
        self.replies: list[str] = []
        self.answers: list[tuple] = []

    def message_handler(self, commands=None, func=None):  # noqa: ANN001, ANN201
        def decorator(fn):  # noqa: ANN001, ANN202
            for command in commands or []:
                self.handlers[command] = fn
            if func is not None and not commands:
                self.reason_handler = fn
            return fn

        return decorator

    def callback_query_handler(self, func=None):  # noqa: ANN001, ANN201
        def decorator(fn):  # noqa: ANN001, ANN202
            self.callback = fn
            return fn

        return decorator

    def reply_to(self, message, text: str, **_kwargs) -> None:  # noqa: ANN001
        self.replies.append(text)

    def answer_callback_query(self, call_id, text=None) -> None:  # noqa: ANN001
        self.answers.append((call_id, text))

    def send_message(self, chat_id, text: str, **_kwargs) -> None:  # noqa: ANN001
        self.replies.append(text)


def _settings(monkeypatch, *, chat: str, owner_user: str | None) -> None:
    from titan.config.settings import get_settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", chat)
    if owner_user is None:
        monkeypatch.delenv("TELEGRAM_OWNER_USER_ID", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_OWNER_USER_ID", owner_user)
    get_settings.cache_clear()
    _cmd_rate.clear()


@pytest.fixture(autouse=True)
def _clear_settings():
    from titan.config.settings import get_settings

    yield
    get_settings.cache_clear()
    _cmd_rate.clear()


def _bot() -> TitanTelegramBot:
    bot = TitanTelegramBot(bot_token="")
    fake = _FakeTeleBot()
    bot.bot = fake
    bot._register_handlers()
    bot.fake = fake
    bot.cmd_callbacks["stats"] = lambda: "stats for the owner"
    return bot


def _message(chat_id: int, user_id: int | None, text: str = "/stats") -> SimpleNamespace:
    user = None if user_id is None else SimpleNamespace(id=user_id)
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id), from_user=user, text=text)


@pytest.mark.unit
def test_in_the_group_the_owners_command_runs(monkeypatch) -> None:
    _settings(monkeypatch, chat=str(GROUP), owner_user=str(OWNER_USER))
    bot = _bot()
    bot.fake.handlers["stats"](_message(GROUP, OWNER_USER))
    assert bot.fake.replies == ["stats for the owner"]


@pytest.mark.unit
def test_in_the_group_another_members_command_gets_no_reply(monkeypatch) -> None:
    _settings(monkeypatch, chat=str(GROUP), owner_user=str(OWNER_USER))
    bot = _bot()
    for command in ("stats", "help", "sync", "stop", "consent"):
        bot.fake.handlers[command](_message(GROUP, MEMBER_USER, f"/{command}"))
    assert bot.fake.replies == []


@pytest.mark.unit
def test_in_the_group_a_sender_telegram_does_not_name_is_not_the_owner(monkeypatch) -> None:
    """An anonymous admin or a channel post has no from_user (or Telegram's stand-in id)."""
    _settings(monkeypatch, chat=str(GROUP), owner_user=str(OWNER_USER))
    bot = _bot()
    bot.fake.handlers["stats"](_message(GROUP, None))
    bot.fake.handlers["stats"](SimpleNamespace(chat=SimpleNamespace(id=GROUP), text="/stats"))
    assert bot.fake.replies == []


@pytest.mark.unit
def test_in_the_group_without_the_owners_user_id_nobody_is_trusted(monkeypatch, caplog) -> None:
    _settings(monkeypatch, chat=str(GROUP), owner_user=None)
    bot = _bot()
    with caplog.at_level(logging.CRITICAL, logger="titan.integrations.telegram_bot"):
        bot.fake.handlers["stats"](_message(GROUP, OWNER_USER))
    assert bot.fake.replies == []
    assert any("group_owner_user_not_configured" in r.getMessage() for r in caplog.records)


@pytest.mark.unit
def test_in_the_group_another_member_cannot_press_the_override_button(monkeypatch) -> None:
    _settings(monkeypatch, chat=str(GROUP), owner_user=str(OWNER_USER))
    bot = _bot()
    processed: list = []
    monkeypatch.setattr(bot, "process_override_callback", lambda *a: processed.append(a) or "ok")
    call = SimpleNamespace(
        id="c1",
        data="override:request:d1",
        message=SimpleNamespace(chat=SimpleNamespace(id=GROUP), from_user=SimpleNamespace(id=999)),
        from_user=SimpleNamespace(id=MEMBER_USER),
    )
    bot.fake.callback(call)
    assert processed == []
    assert bot.fake.answers == [("c1", None)]

    call.from_user = SimpleNamespace(id=OWNER_USER)
    bot.fake.callback(call)
    assert len(processed) == 1


@pytest.mark.unit
def test_in_the_group_another_member_cannot_give_the_override_reason(monkeypatch) -> None:
    _settings(monkeypatch, chat=str(GROUP), owner_user=str(OWNER_USER))
    bot = _bot()
    reasons: list = []
    monkeypatch.setattr(bot, "process_override_reason", lambda chat, text: reasons.append(text) or "ok")
    bot._pending_override_prompts[GROUP] = {"decision_id": "d1", "athlete_id": "owner", "awaiting_reason": "1"}
    bot.fake.reason_handler(_message(GROUP, MEMBER_USER, "not the owner"))
    bot.fake.reason_handler(_message(GROUP, OWNER_USER, "the owner's reason"))
    assert reasons == ["the owner's reason"]


@pytest.mark.unit
def test_a_private_chat_needs_no_owner_user_id(monkeypatch) -> None:
    """Only the owner writes in their private chat: unchanged, with or without the setting."""
    _settings(monkeypatch, chat=str(PRIVATE_OWNER_CHAT), owner_user=None)
    bot = _bot()
    bot.fake.handlers["stats"](SimpleNamespace(chat=SimpleNamespace(id=PRIVATE_OWNER_CHAT), text="/stats"))
    assert bot.fake.replies == ["stats for the owner"]
