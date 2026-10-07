"""INV-22 (AGENTS §8.13, T-PRA-21, plan #21δ): Telegram /sync, /manual_entry and override
write their audit row durably before the effect; if the row cannot be written the
command is rejected and nothing changes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from titan.core.database import DatabaseManager
from titan.integrations.telegram_bot import (
    _AUDIT_UNAVAILABLE_REPLY,
    TitanTelegramBot,
    _cmd_rate,
    _create_override_nonce,
)

CHAT = 321


class _FakeTeleBot:
    def __init__(self) -> None:
        self.handlers: dict = {}
        self.replies: list[str] = []

    def message_handler(self, commands=None, func=None):  # noqa: ANN001, ANN201
        def decorator(fn):  # noqa: ANN001, ANN202
            for command in commands or []:
                self.handlers[command] = fn
            return fn

        return decorator

    def callback_query_handler(self, func=None):  # noqa: ANN001, ANN201
        return lambda fn: fn

    def reply_to(self, message, text: str) -> None:  # noqa: ANN001
        self.replies.append(text)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    counted: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        "titan.observability.metrics.get_metrics",
        lambda: SimpleNamespace(counter=lambda name, *a, labels=None, **k: counted.append((name, labels))),
    )
    db = DatabaseManager(db_dir=tmp_path)
    bot = TitanTelegramBot(bot_token="", chat_id=CHAT, db=db)
    bot.register_override_callback("db_provider", lambda: db)
    _cmd_rate.clear()
    yield SimpleNamespace(db=db, bot=bot, counted=counted)
    db.close()


def _break_audit(monkeypatch: pytest.MonkeyPatch, db: DatabaseManager) -> None:
    def _fail(**_kwargs):  # noqa: ANN202
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "log_coach_action", _fail)


def _audit_actions(db: DatabaseManager) -> list[str]:
    return [row["action_type"] for row in db.get_coach_audit_log()]


def _override_rows(db: DatabaseManager) -> int:
    return db.conn.execute("SELECT COUNT(*) FROM override_signals").fetchone()[0]


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _ask_for_override_reason(bot: TitanTelegramBot) -> None:
    bot._pending_override_prompts[CHAT] = {
        "decision_id": "d-1",
        "athlete_id": "owner",
        "created_at": datetime.now(UTC).isoformat(),
    }
    nonce = _create_override_nonce("d-1")
    assert "reason" in bot.process_override_callback(CHAT, f"override:request:{nonce}")


def test_manual_entry_writes_its_audit_row_first(env) -> None:
    assert env.bot.handle_manual_entry_text("HRV=65 RHR=52", chat_id=CHAT).startswith("✅")

    rows = env.db.get_coach_audit_log()
    assert [r["action_type"] for r in rows] == ["TELEGRAM_MANUAL_ENTRY"]
    assert rows[0]["coach_id"] == f"telegram:{CHAT}"
    assert env.db.get_daily_metric(_today())["hrv_rmssd"] == 65


def test_manual_entry_is_rejected_when_the_audit_write_fails(env, monkeypatch) -> None:
    _break_audit(monkeypatch, env.db)

    assert env.bot.handle_manual_entry_text("HRV=65", chat_id=CHAT) == _AUDIT_UNAVAILABLE_REPLY

    assert env.db.get_daily_metric(_today()) is None
    assert env.counted == [("audit_write_failure", {"surface": "telegram"})]


def test_override_writes_its_audit_row_first(env) -> None:
    _ask_for_override_reason(env.bot)

    assert env.bot.process_override_reason(CHAT, "legs heavy") == "✅ Override recorded."

    assert _audit_actions(env.db) == ["TELEGRAM_OVERRIDE"]
    assert _override_rows(env.db) == 1


def test_override_is_rejected_when_the_audit_write_fails(env, monkeypatch) -> None:
    _ask_for_override_reason(env.bot)
    _break_audit(monkeypatch, env.db)

    assert env.bot.process_override_reason(CHAT, "legs heavy") == _AUDIT_UNAVAILABLE_REPLY

    assert _override_rows(env.db) == 0
    assert env.counted == [("audit_write_failure", {"surface": "telegram"})]


def _send_sync(bot: TitanTelegramBot) -> _FakeTeleBot:
    fake = _FakeTeleBot()
    bot.bot = fake
    bot._register_handlers()
    fake.handlers["sync"](SimpleNamespace(chat=SimpleNamespace(id=CHAT)))
    return fake


def test_sync_writes_its_audit_row_before_syncing(env) -> None:
    seen: list[list[str]] = []
    env.bot.cmd_callbacks["sync"] = lambda: seen.append(_audit_actions(env.db)) or "SYNCED"

    fake = _send_sync(env.bot)

    assert seen == [["TELEGRAM_SYNC"]]
    assert fake.replies[-1] == "SYNCED"


def test_sync_is_rejected_when_the_audit_write_fails(env, monkeypatch) -> None:
    synced: list[bool] = []
    env.bot.cmd_callbacks["sync"] = lambda: synced.append(True) or "SYNCED"
    _break_audit(monkeypatch, env.db)

    fake = _send_sync(env.bot)

    assert synced == []
    assert fake.replies == [_AUDIT_UNAVAILABLE_REPLY]
    assert env.counted == [("audit_write_failure", {"surface": "telegram"})]


def test_sync_is_rejected_without_a_database(env) -> None:
    synced: list[bool] = []
    env.bot.db = None
    env.bot.cmd_callbacks["sync"] = lambda: synced.append(True) or "SYNCED"

    fake = _send_sync(env.bot)

    assert synced == []
    assert fake.replies == [_AUDIT_UNAVAILABLE_REPLY]
