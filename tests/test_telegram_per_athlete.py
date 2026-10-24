"""Phase 4 step 5: Telegram per athlete (ADR-0067 D10; D-094).

- One bot, one process: the owner's polling bot also routes each athlete's private chat.
- A chat that is not registered gets no reply and learns nothing about other athletes.
- An athlete has /sync and /stop only; each writes its audit row first, for that athlete.
- An athlete's messages go to their own chat, never the owner's.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from titan.core.athlete import AthleteNotReady
from titan.core.database import DatabaseManager
from titan.integrations.garmin_sync import GarminSync, athlete_token_path, encrypt_athlete_token
from titan.integrations.telegram_bot import (
    _AUDIT_UNAVAILABLE_REPLY,
    TitanTelegramBot,
    _cmd_rate,
)

_A, _B = "a-0000000a", "a-0000000b"
OWNER_CHAT, CHAT_A, CHAT_B, STRANGER = 1000, 2000, 3000, 9999
_PROFILE = {
    "birth_date": "1988-07-02", "sex": "M", "weight_kg": 70.0, "height_cm": 178,
    "max_hr": 188, "threshold_hr": 168, "training_phase": "BUILD", "training_goal": "10K",
    "location_city": "Larissa", "location_country": "GR",
}


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


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER_CHAT))
    # Athletes' chats are routed only with multi-athlete mode on (MA-F9, D-119).
    monkeypatch.setenv("TITAN_MULTI_ATHLETE", "1")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    _cmd_rate.clear()
    yield data
    get_settings.cache_clear()


@pytest.fixture
def db(data_dir):
    manager = DatabaseManager(db_dir=data_dir)
    for athlete in (_A, _B):
        manager.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')",
            (athlete, athlete),
        )
    manager.conn.commit()
    manager.bind_telegram_chat(_A, CHAT_A)
    manager.bind_telegram_chat(_B, CHAT_B)
    yield manager
    manager.close()


@pytest.fixture
def bot(db):
    """The owner's polling bot, with every handler registered on a fake TeleBot."""
    owner_bot = TitanTelegramBot(bot_token="", db=db)
    fake = _FakeTeleBot()
    owner_bot.bot = fake
    owner_bot._register_handlers()
    owner_bot.fake = fake
    return owner_bot


def _send(bot: TitanTelegramBot, command: str, chat_id: int) -> list[str]:
    before = len(bot.fake.replies)
    bot.fake.handlers[command](SimpleNamespace(chat=SimpleNamespace(id=chat_id), text=f"/{command}"))
    return [text for _chat, text in bot.fake.replies[before:]]


def _audit(db: DatabaseManager) -> list[tuple[str, str, str]]:
    return [(r["coach_id"], r["athlete_id"], r["action_type"]) for r in reversed(db.get_coach_audit_log())]


def _grant_consent(db: DatabaseManager, athlete_id: str) -> None:
    db.conn.execute(
        "INSERT INTO consent_log (athlete_id, consent_type, text_version, granted_at, revoked_at, channel) "
        "VALUES (?, 'coaching', 'v1', '2026-01-01T00:00:00+00:00', NULL, 'telegram')",
        (athlete_id,),
    )
    db.conn.commit()


def _open_consents(db: DatabaseManager) -> list[str]:
    rows = db.conn.execute("SELECT athlete_id FROM consent_log WHERE revoked_at IS NULL ORDER BY athlete_id")
    return [r[0] for r in rows.fetchall()]


# ── Binding a chat ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_each_chat_belongs_to_one_athlete(db) -> None:
    assert db.get_athlete_for_telegram_chat(CHAT_A) == _A
    assert db.get_athlete_for_telegram_chat(str(CHAT_B)) == _B
    assert db.get_athlete_for_telegram_chat(STRANGER) is None
    db.bind_telegram_chat(_A, CHAT_A)  # binding the same chat again changes nothing
    with pytest.raises(ValueError, match="already bound to another athlete"):
        db.bind_telegram_chat(_B, CHAT_A)
    assert db.get_athlete_account(_B)["telegram_chat_id"] == str(CHAT_B)


@pytest.mark.unit
def test_the_owner_and_the_owners_chat_are_never_bound(db) -> None:
    with pytest.raises(ValueError, match="lives in .env"):
        db.bind_telegram_chat("owner", 4000)
    with pytest.raises(ValueError, match="the owner's"):
        db.bind_telegram_chat(_A, OWNER_CHAT)
    with pytest.raises(ValueError, match="required"):
        db.bind_telegram_chat(_A, " ")


@pytest.mark.unit
def test_a_telegram_chat_alone_leaves_garmin_missing(db) -> None:
    account = db.get_athlete_account(_A)
    assert account["garmin_user_id"] is None
    assert account["garmin_token_state"] == "missing"


# ── Inbound chats ─────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.parametrize("command", ["start", "help", "sync", "stop", "today", "stats", "calibration"])
def test_an_unregistered_chat_gets_no_reply(bot, db, command) -> None:
    _grant_consent(db, _A)
    bot.register_athlete_command("sync", lambda athlete_id: pytest.fail("synced for a stranger"))

    assert _send(bot, command, STRANGER) == []
    assert _audit(db) == []
    assert _open_consents(db) == [_A]


@pytest.mark.integration
@pytest.mark.parametrize("command", ["today", "week", "stats", "recovery", "activities", "calibration"])
def test_an_athlete_has_no_owner_command(bot, command) -> None:
    bot.register_command(command, lambda: pytest.fail("an athlete reached an owner command"))

    assert _send(bot, command, CHAT_A) == []


@pytest.mark.integration
def test_an_athletes_help_lists_sync_and_stop_only(bot) -> None:
    (text,) = _send(bot, "help", CHAT_A)
    assert "/sync" in text and "/stop" in text
    assert "/today" not in text and "/calibration" not in text


@pytest.mark.integration
def test_an_athletes_sync_audits_first_and_syncs_that_athlete_only(bot, db) -> None:
    _grant_consent(db, _A)
    seen: list[tuple[str, list]] = []
    bot.register_athlete_command("sync", lambda athlete_id: seen.append((athlete_id, _audit(db))) or "done")
    bot.register_command("sync", lambda: pytest.fail("the owner's sync ran for an athlete"))

    assert _send(bot, "sync", CHAT_A) == ["done"]

    assert seen == [(_A, [(f"telegram:{CHAT_A}", _A, "TELEGRAM_SYNC")])]
    assert _audit(db) == [(f"telegram:{CHAT_A}", _A, "TELEGRAM_SYNC")]


@pytest.mark.integration
def test_an_athletes_sync_without_its_audit_row_does_nothing(bot, db, monkeypatch) -> None:
    _grant_consent(db, _A)
    bot.register_athlete_command("sync", lambda athlete_id: pytest.fail("synced without an audit row"))
    monkeypatch.setattr(db, "log_coach_action", MagicMock(side_effect=RuntimeError("disk full")))
    monkeypatch.setattr(
        "titan.observability.metrics.get_metrics", lambda: SimpleNamespace(counter=lambda *a, **k: None)
    )

    assert _send(bot, "sync", CHAT_A) == [_AUDIT_UNAVAILABLE_REPLY]


@pytest.mark.integration
def test_the_owners_sync_is_unchanged(bot, db) -> None:
    bot.register_command("sync", lambda: "owner synced")
    bot.register_athlete_command("sync", lambda athlete_id: pytest.fail("athlete sync ran for the owner"))

    replies = _send(bot, "sync", OWNER_CHAT)

    assert replies[-1] == "owner synced"
    assert _audit(db) == [(f"telegram:{OWNER_CHAT}", "owner", "TELEGRAM_SYNC")]


@pytest.mark.integration
def test_an_athletes_stop_audits_first_and_revokes_that_athlete_only(bot, db) -> None:
    _grant_consent(db, _A)
    _grant_consent(db, _B)

    (text,) = _send(bot, "stop", CHAT_A)

    assert text.startswith("⏹")
    assert _audit(db) == [(f"telegram:{CHAT_A}", _A, "TELEGRAM_STOP")]
    assert _open_consents(db) == [_B]


@pytest.mark.integration
def test_an_athletes_stop_without_its_audit_row_revokes_nothing(bot, db, monkeypatch) -> None:
    _grant_consent(db, _A)
    monkeypatch.setattr(db, "log_coach_action", MagicMock(side_effect=RuntimeError("disk full")))
    monkeypatch.setattr(
        "titan.observability.metrics.get_metrics", lambda: SimpleNamespace(counter=lambda *a, **k: None)
    )

    assert _send(bot, "stop", CHAT_A) == [_AUDIT_UNAVAILABLE_REPLY]
    assert _open_consents(db) == [_A]


@pytest.mark.integration
def test_the_owners_stop_changes_nothing(bot, db) -> None:
    _grant_consent(db, _A)

    (text,) = _send(bot, "stop", OWNER_CHAT)

    assert "owner" in text
    assert _audit(db) == []
    assert _open_consents(db) == [_A]


@pytest.mark.unit
def test_athletes_can_be_given_their_own_commands_only(bot) -> None:
    with pytest.raises(ValueError, match="only"):
        bot.register_athlete_command("today", lambda athlete_id: "")


@pytest.mark.integration
def test_a_chat_written_for_the_owner_is_never_routed(bot, db) -> None:
    # bind_telegram_chat refuses the owner; a row written directly must not route either.
    db.conn.execute(
        "INSERT INTO athlete_accounts (athlete_id, garmin_token_state, telegram_chat_id, updated_at) "
        "VALUES ('owner', 'missing', '5000', 'now')"
    )
    db.conn.commit()
    bot.register_athlete_command("sync", lambda athlete_id: pytest.fail(f"routed to {athlete_id}"))

    assert _send(bot, "sync", 5000) == []


@pytest.mark.integration
def test_a_failed_lookup_is_an_unregistered_chat(bot, db, monkeypatch) -> None:
    monkeypatch.setattr(db, "get_athlete_for_telegram_chat", MagicMock(side_effect=RuntimeError("db locked")))

    assert _send(bot, "sync", CHAT_A) == []


# ── Outbound messages ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_an_athletes_bot_never_falls_back_to_the_owners_chat(data_dir) -> None:
    with pytest.raises(ValueError, match="their own Telegram chat"):
        TitanTelegramBot(bot_token="", athlete_id=_A)

    athlete_bot = TitanTelegramBot(bot_token="", chat_id=str(CHAT_A), athlete_id=_A)

    assert athlete_bot.chat_id == CHAT_A
    assert athlete_bot._is_trusted(CHAT_A) is False
    assert athlete_bot._is_trusted(OWNER_CHAT) is False


@pytest.mark.unit
def test_an_athletes_decision_comes_without_override_buttons(data_dir, monkeypatch) -> None:
    athlete_bot = TitanTelegramBot(bot_token="", chat_id=str(CHAT_A), athlete_id=_A)
    sent: list[str] = []
    monkeypatch.setattr(athlete_bot, "send_message", lambda text, parse_mode="Markdown": sent.append(text) or True)

    assert athlete_bot.send_governance_decision(text="EASY", decision_id="d-1", decision_type="EASY", athlete_id=_A)

    assert sent == ["EASY"]
    assert athlete_bot._pending_override_prompts == {}


# ── Worker ────────────────────────────────────────────────────────────────────


def _ready(db: DatabaseManager, athlete_id: str) -> None:
    _grant_consent(db, athlete_id)
    db.save_athlete_profile(athlete_id, _PROFILE)
    db.bind_garmin_account(athlete_id, f"garmin-{athlete_id}")
    db.set_garmin_token_state(athlete_id, "ok")
    from titan.integrations.garmin_sync import (
        athlete_token_path,  # a ready athlete has the token file (MA-F2)
    )
    athlete_token_path(athlete_id).parent.mkdir(parents=True, exist_ok=True)
    athlete_token_path(athlete_id).write_bytes(b"synthetic-token")


@pytest.mark.integration
def test_the_worker_builds_nothing_for_an_athlete_without_a_chat(data_dir) -> None:
    from titan import worker

    manager = DatabaseManager(db_dir=data_dir)
    manager.conn.execute("INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, 'A', 'now')", (_A,))
    manager.conn.commit()
    _ready(manager, _A)
    try:
        with pytest.raises(AthleteNotReady, match="telegram: no chat bound"):
            worker._build_daily_coach(manager, athlete_id=_A)
    finally:
        manager.close()


@pytest.mark.integration
def test_the_worker_sends_an_athletes_morning_to_their_own_chat(db) -> None:
    from titan import worker

    _ready(db, _A)

    coach = worker._build_daily_coach(db, athlete_id=_A)
    owner_coach = worker._build_daily_coach(db)

    assert coach.telegram.chat_id == CHAT_A
    assert coach.telegram.athlete_id == _A
    assert owner_coach.telegram.chat_id == OWNER_CHAT
    assert owner_coach.telegram.athlete_id == "owner"


# ── /sync for an athlete ──────────────────────────────────────────────────────


@pytest.fixture
def key_file(tmp_path, data_dir, monkeypatch):
    path = tmp_path / "keys" / "athletes.key"
    path.parent.mkdir()
    path.write_bytes(Fernet.generate_key())
    os.chmod(path, 0o600)
    monkeypatch.setenv("TITAN_TOKEN_KEY_FILE", str(path))
    return path


def _fake_garminconnect(monkeypatch) -> dict:
    seen = {"logins": 0}

    class _Garth:
        token = ""

        def loads(self, data: str) -> None:
            self.token = data

    class _Garmin:
        def __init__(self, *args) -> None:
            self.client = _Garth()

        def connectapi(self, _path):
            # The token "session-of-a" belongs to the Garmin account bound to athlete A (MA-F1).
            return {"displayName": f"garmin-{_A}" if self.client.token == "session-of-a" else "garmin-other"}

        def login(self):
            seen["logins"] += 1

    module = MagicMock()
    module.Garmin = _Garmin
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    return seen


class _ActivityClient:
    def __init__(self, activities: list[dict]) -> None:
        self._activities = activities

    def get_activities_by_date(self, _start, _end, _activity_type):
        return self._activities


def _run(start: str, activity_id: int) -> dict:
    return {
        "startTimeLocal": start, "activityType": {"typeKey": "running"}, "distance": 8000,
        "duration": 1800, "averageHeartRate": 150, "maxHeartRate": 170, "calories": 400,
        "elevationGain": 20, "activityId": activity_id,
    }


@pytest.mark.integration
def test_an_athletes_sync_writes_only_that_athletes_data(db, key_file, monkeypatch) -> None:
    from titan import worker

    seen = _fake_garminconnect(monkeypatch)
    _ready(db, _A)
    _ready(db, _B)
    path = athlete_token_path(_A)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_athlete_token("session-of-a"))

    def _sync_all(self, days_back: int = 14) -> dict:
        self.client = _ActivityClient([_run("2026-10-15T07:00:00", 701)])
        return {"activities": self.sync_activities(days_back=3)}

    monkeypatch.setattr(GarminSync, "sync_all", _sync_all)
    monkeypatch.setattr(worker, "_utc_now", lambda: datetime(2026, 10, 15, 9, 0, tzinfo=UTC))

    assert worker.sync_athlete_on_request(db, _A) == "✅ Sync complete."

    rows = db.conn.execute("SELECT athlete_id, garmin_activity_id FROM training_log").fetchall()
    assert [(r[0], str(r[1])) for r in rows] == [(_A, "701")]
    assert seen["logins"] == 0


@pytest.mark.integration
def test_an_athletes_sync_without_a_token_pauses_them(db, key_file, monkeypatch) -> None:
    from titan import worker

    seen = _fake_garminconnect(monkeypatch)
    _ready(db, _A)
    athlete_token_path(_A).unlink()  # the DB still says 'ok', the token file is gone (MA-F2)

    assert "not complete" in worker.sync_athlete_on_request(db, _A)
    assert db.get_athlete_account(_A)["garmin_token_state"] == "expired"
    assert seen["logins"] == 0


@pytest.mark.integration
def test_an_incomplete_athletes_sync_calls_nothing(db, monkeypatch) -> None:
    from titan import worker

    monkeypatch.setattr(GarminSync, "__init__", lambda *a, **k: pytest.fail("Garmin built for an incomplete athlete"))

    assert "not complete" in worker.sync_athlete_on_request(db, _A)
    assert db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()[0] == 0


@pytest.mark.unit
def test_the_athlete_sync_is_not_for_the_owner(db) -> None:
    from titan import worker

    with pytest.raises(ValueError, match="owner"):
        worker.sync_athlete_on_request(db, "owner")


# ── M0-03: an athlete's /sync stores the training load ─────────────────────────


def _athlete_sync_of(db, monkeypatch, activities: list[dict]) -> None:
    """An athlete's /sync as the worker runs it, through the real GarminSync.sync_all path."""
    from titan import worker

    _fake_garminconnect(monkeypatch)
    _ready(db, _A)
    path = athlete_token_path(_A)
    path.write_bytes(encrypt_athlete_token("session-of-a"))

    def _sync_all(self, days_back: int = 14) -> dict:
        self.client = _ActivityClient(activities)
        # What _sync_operation passes: the instance's max HR, not the 0 default.
        return {"activities": self.sync_activities(days_back=3, athlete_max_hr=self.athlete_max_hr)}

    monkeypatch.setattr(GarminSync, "sync_all", _sync_all)
    monkeypatch.setattr(worker, "_utc_now", lambda: datetime(2026, 10, 15, 9, 0, tzinfo=UTC))
    assert worker.sync_athlete_on_request(db, _A) == "✅ Sync complete."


def _stored_load(db, activity_id: str) -> int:
    return db.conn.execute(
        "SELECT training_load FROM training_log WHERE athlete_id = ? AND garmin_activity_id = ?",
        (_A, activity_id),
    ).fetchone()[0]


@pytest.mark.integration
def test_an_athletes_sync_stores_the_load_from_their_max_hr(db, key_file, monkeypatch) -> None:
    """Before M0-03 the /sync GarminSync had no max HR, so every run was stored with load 0."""
    from titan.science.trimp_engine import TRIMPEngine

    _athlete_sync_of(db, monkeypatch, [_run("2026-10-15T07:00:00", 701)])

    expected, _ = TRIMPEngine.calculate_edwards_trimp(30.0, 150, _PROFILE["max_hr"])
    assert expected > 0
    assert _stored_load(db, "701") == int(round(expected, 1))


@pytest.mark.integration
def test_an_athletes_sync_does_not_erase_a_load_stored_before(db, key_file, monkeypatch) -> None:
    """The morning stored the run with its load; an evening /sync sees it again (D-080)."""
    db.save_session(
        date="2026-10-15", session_type="EASY", distance_km=8.0, duration_sec=1800,
        avg_hr=150, max_hr=170, training_load=77, garmin_activity_id=701, athlete_id=_A,
    )

    _athlete_sync_of(db, monkeypatch, [_run("2026-10-15T07:00:00", 701)])

    from titan.science.trimp_engine import TRIMPEngine

    expected, _ = TRIMPEngine.calculate_edwards_trimp(30.0, 150, _PROFILE["max_hr"])
    assert _stored_load(db, "701") == int(round(expected, 1))  # the recomputed load, never 0


@pytest.mark.integration
def test_a_load_that_could_not_be_computed_keeps_the_stored_one(db) -> None:
    """A re-seen activity with load 0 (no max HR) keeps the computed load; a new value replaces it."""
    common = {
        "date": "2026-10-15", "session_type": "EASY", "distance_km": 8.0, "duration_sec": 1800,
        "avg_hr": 150, "max_hr": 170, "garmin_activity_id": 702, "athlete_id": _A,
    }
    db.save_session(training_load=77, **common)

    db.save_session(training_load=None, **common)
    assert _stored_load(db, "702") == 77

    db.save_session(training_load=81, **common)
    assert _stored_load(db, "702") == 81
