"""Phase 4 step 12b: the worker answers the athletes' commands (finding К-1, D-103).

- With TITAN_MULTI_ATHLETE=1 the worker starts the Telegram listener and stops it on shutdown.
- Without a bot token nothing listens and the round still runs.
- The single-owner loop does not listen.
- /consent, /agree, /sync and /stop from an athlete's chat reach the database through the
  worker's bot, each for that athlete only.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from titan import worker
from titan.core.athlete import CONSENT_TEXT_VERSION
from titan.core.database import DatabaseManager
from titan.integrations.telegram_bot import _cmd_rate

pytestmark = pytest.mark.integration

_A, _B = "a-0000000a", "a-0000000b"
OWNER_CHAT, CHAT_A, CHAT_B = 1000, 2000, 3000


class _FakeTeleBot:
    def __init__(self) -> None:
        self.handlers: dict = {}
        self.replies: list[tuple[int, str]] = []

    def message_handler(self, commands=None, func=None):  # noqa: ANN001, ANN201
        def decorator(fn):  # noqa: ANN001, ANN202
            for command in commands or []:
                self.handlers[command] = fn
            return fn

        return decorator

    def callback_query_handler(self, func=None):  # noqa: ANN001, ANN201
        return lambda fn: fn

    def reply_to(self, message, text: str, **_kwargs) -> None:  # noqa: ANN001
        self.replies.append((message.chat.id, text))


class _RecordingBot:
    """Stands in for TitanTelegramBot: records what the worker does with it."""

    events: list[str] = []
    has_token = True

    def __init__(self, *_args, **_kwargs) -> None:
        self.bot = object() if type(self).has_token else None
        self.athlete_cmd_callbacks: dict = {}

    def register_athlete_command(self, command: str, callback) -> None:  # noqa: ANN001
        self.athlete_cmd_callbacks[command] = callback
        type(self).events.append(f"register:{command}")

    def start_bot(self) -> None:
        type(self).events.append("start")

    def stop_bot(self) -> None:
        type(self).events.append("stop")


@pytest.fixture
def db(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER_CHAT))
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    _cmd_rate.clear()
    _RecordingBot.events = []
    _RecordingBot.has_token = True
    manager = DatabaseManager(db_dir=data)
    for athlete, chat in ((_A, CHAT_A), (_B, CHAT_B)):
        manager.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')",
            (athlete, athlete),
        )
        manager.conn.commit()
        manager.bind_telegram_chat(athlete, chat)
    yield manager
    manager.close()
    get_settings.cache_clear()


def _run_scheduler_once(db: DatabaseManager, monkeypatch) -> None:
    """Run _run_with_scheduler for one process lifetime, with no real scheduler thread."""
    import titan.orchestration.coaching_scheduler as cs

    class _FakeScheduler:
        def __init__(self, interval_seconds: float) -> None:
            pass

        def register_athlete(self, athlete_id, callback) -> None:  # noqa: ANN001
            _RecordingBot.events.append(f"round:{athlete_id}")

        def start(self) -> None:
            _RecordingBot.events.append("scheduler_start")

        def stop(self) -> None:
            _RecordingBot.events.append("scheduler_stop")

    monkeypatch.setattr(cs, "CoachingScheduler", _FakeScheduler)
    monkeypatch.setattr(worker, "_supervise_scheduler", lambda *a, **k: None)
    worker._run_with_scheduler(db, threading.Event())


def test_multi_athlete_worker_listens_and_stops_listening_on_shutdown(db, monkeypatch) -> None:
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _RecordingBot)

    _run_scheduler_once(db, monkeypatch)

    assert _RecordingBot.events == [
        "round:round", "register:sync", "start", "scheduler_start", "scheduler_stop", "stop",
    ]


def test_the_listener_stops_even_when_supervision_fails(db, monkeypatch) -> None:
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _RecordingBot)

    def _boom(*_a, **_k) -> None:
        raise RuntimeError("supervisor died")

    import titan.orchestration.coaching_scheduler as cs

    monkeypatch.setattr(cs, "CoachingScheduler", lambda interval_seconds: SimpleNamespace(
        register_athlete=lambda *_a: None, start=lambda: None, stop=lambda: None,
    ))
    monkeypatch.setattr(worker, "_supervise_scheduler", _boom)

    with pytest.raises(RuntimeError, match="supervisor died"):
        worker._run_with_scheduler(db, threading.Event())

    assert _RecordingBot.events[-1] == "stop"


def test_without_a_bot_token_nothing_listens_and_the_round_runs(db, monkeypatch, caplog) -> None:
    import titan.integrations.telegram_bot as telegram_bot

    _RecordingBot.has_token = False
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _RecordingBot)

    _run_scheduler_once(db, monkeypatch)

    assert "start" not in _RecordingBot.events
    assert "stop" not in _RecordingBot.events
    assert "scheduler_start" in _RecordingBot.events
    assert any(r.getMessage() == "command_listener_not_started" for r in caplog.records)


def test_the_single_owner_loop_does_not_listen(db, monkeypatch, tmp_path) -> None:
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setenv("TITAN_MULTI_ATHLETE", "0")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _RecordingBot)
    monkeypatch.setattr(worker, "_run_backup", lambda _db: None)
    monkeypatch.setattr(worker, "_run_due_routine", lambda *a, **k: True)  # exits after one pass

    worker.run_forever(str(tmp_path / "data" / "titan_core.db"), shutdown_event=threading.Event())

    assert "start" not in _RecordingBot.events


# ── The worker's bot, end to end on a fake TeleBot ───────────────────────────


@pytest.fixture
def worker_bot(db):
    bot = worker._command_bot(db)
    fake = _FakeTeleBot()
    bot.bot = fake
    bot._register_handlers()
    bot.fake = fake
    return bot


def _send(bot, text: str, chat_id: int) -> list[str]:  # noqa: ANN001
    command = text.split()[0].lstrip("/")
    before = len(bot.fake.replies)
    bot.fake.handlers[command](SimpleNamespace(chat=SimpleNamespace(id=chat_id), text=text))
    return [reply for _chat, reply in bot.fake.replies[before:]]


def test_consent_and_agree_reach_the_database_through_the_worker(worker_bot, db) -> None:
    shown = _send(worker_bot, "/consent", CHAT_A)
    assert f"/agree {CONSENT_TEXT_VERSION}" in shown[0]

    reply = _send(worker_bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_A)

    assert "is recorded" in reply[0]
    assert db.has_current_consent(_A)
    assert not db.has_current_consent(_B)


def test_stop_from_an_athlete_withdraws_only_that_athletes_consent(worker_bot, db) -> None:
    _send(worker_bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_A)
    _send(worker_bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_B)

    _send(worker_bot, "/stop", CHAT_A)

    assert not db.has_current_consent(_A)
    assert db.has_current_consent(_B)


def test_sync_from_an_athlete_runs_the_worker_sync_for_that_athlete(worker_bot, db, monkeypatch) -> None:
    synced: list[str] = []
    monkeypatch.setattr(worker, "sync_athlete_on_request", lambda _db, athlete_id: synced.append(athlete_id) or "ok")
    _send(worker_bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_A)

    assert _send(worker_bot, "/sync", CHAT_A) == ["ok"]
    assert synced == [_A]
