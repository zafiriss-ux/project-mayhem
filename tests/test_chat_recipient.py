"""D-107: no message to the wrong person (audit RC-01 .. RC-04).

- RC-01: a Telegram chat id has one canonical form, a positive decimal integer stored as
  ``str(int(x))``. It is the form that is checked, stored, looked up and sent to, so
  "01001", "+1001" or "1_001" can no longer pass as a chat other than the one they reach.
  A chat stored before in another form is not run (fail closed) and Zaf is told.
- RC-02: an operator alert about another athlete reaches Zaf with the athlete id; the
  athlete gets a short message without operator instructions.
- RC-03: with no bot nothing was sent, so ``send_message`` is False and the day is not
  recorded as delivered.
- RC-04: no athlete chat is bound while the owner's TELEGRAM_CHAT_ID is empty.

Only obviously fake values: chats 1, 1001, 1002; athlete ids a-0000000a/b/c.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from titan.core import athlete_lifecycle as lifecycle
from titan.core.athlete import canonical_chat_id
from titan.core.database import DatabaseManager

_A, _B, _C = "a-0000000a", "a-0000000b", "a-0000000c"
_OWNER_CHAT = "1"
_NOW = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
_PROFILE = {
    "birth_date": "1988-07-02", "sex": "F", "weight_kg": 58.0, "height_cm": 165,
    "max_hr": 186, "threshold_hr": 166, "training_phase": "BASE", "training_goal": "10K",
    "location_city": "Volos", "location_country": "GR",
}


def _settings(monkeypatch: pytest.MonkeyPatch, owner_chat: str = _OWNER_CHAT) -> None:
    from titan.config.settings import get_settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", owner_chat)
    get_settings.cache_clear()


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from titan.config.settings import get_settings

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    _settings(monkeypatch)
    manager = DatabaseManager(db_dir=data)
    yield manager
    manager.close()
    get_settings.cache_clear()


def _add(db: DatabaseManager, athlete_id: str, chat: object, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(lifecycle, "new_athlete_id", lambda: athlete_id)
    return lifecycle.add_athlete(db, athlete_id, dict(_PROFILE), chat, now=_NOW)


def _store_legacy_chat(db: DatabaseManager, athlete_id: str, chat: str) -> None:
    """A chat written before D-107, when any stripped text was stored as it was typed."""
    db.conn.execute("UPDATE athlete_accounts SET telegram_chat_id = ? WHERE athlete_id = ?", (chat, athlete_id))
    db.conn.commit()


# ── RC-01: one canonical form ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1001", "1001"), (" 1001 ", "1001"), ("01001", "1001"), (1001, "1001"),
     ("+1001", None), ("1_001", None), ("-1001", None), ("10.01", None), ("0", None),
     ("", None), (None, None), (True, None), ("١٠٠١", None), ("10 01", None)],
)
def test_canonical_chat_id_is_a_positive_decimal_integer(value: object, expected: str | None) -> None:
    assert canonical_chat_id(value) == expected


def test_canonical_chat_id_allows_a_group_for_the_owner_only() -> None:
    assert canonical_chat_id("-100123", allow_negative=True) == "-100123"
    assert canonical_chat_id("-0100123", allow_negative=True) == "-100123"
    assert canonical_chat_id("-100123") is None


@pytest.mark.parametrize("typed", ["01001", "001001", " 1001", "1001 "])
def test_binding_a_second_form_of_a_bound_chat_is_refused(db, monkeypatch, typed: str) -> None:
    _add(db, _A, "1001", monkeypatch)
    with pytest.raises(ValueError, match="already bound"):
        _add(db, _B, typed, monkeypatch)
    assert not lifecycle.athlete_exists(db, _B)


@pytest.mark.parametrize("typed", ["+1001", "1_001", "-1001", "1001.0", "1e3"])
def test_a_chat_id_that_is_not_plain_digits_is_refused(db, monkeypatch, typed: str) -> None:
    with pytest.raises(ValueError, match="positive decimal integer"):
        _add(db, _B, typed, monkeypatch)
    assert not lifecycle.athlete_exists(db, _B)


@pytest.mark.parametrize("typed", ["+1", "01", " 1 ", "001"])
def test_the_owners_chat_in_another_form_is_refused(db, monkeypatch, typed: str) -> None:
    with pytest.raises(ValueError):
        _add(db, _C, typed, monkeypatch)
    assert not lifecycle.athlete_exists(db, _C)


def test_the_owners_chat_set_in_another_form_is_still_the_owners(db, monkeypatch) -> None:
    _settings(monkeypatch, owner_chat="+1")
    with pytest.raises(ValueError):
        _add(db, _C, "1", monkeypatch)


def test_a_second_form_of_a_legacy_row_is_refused(db, monkeypatch) -> None:
    _add(db, _A, "1002", monkeypatch)
    _store_legacy_chat(db, _A, "01001")
    with pytest.raises(ValueError, match="already bound"):
        _add(db, _B, "1001", monkeypatch)
    assert not lifecycle.athlete_exists(db, _B)


def test_the_canonical_form_is_stored_and_found_by_telegrams_own_id(db, monkeypatch) -> None:
    _add(db, _A, " 0001001 ", monkeypatch)
    assert db.get_athlete_account(_A)["telegram_chat_id"] == "1001"
    assert db.get_athlete_for_telegram_chat(1001) == _A
    assert db.get_athlete_for_telegram_chat("1001") == _A
    assert db.get_athlete_for_telegram_chat("+1001") is None
    assert db.get_athlete_for_telegram_chat(-1001) is None
    # Binding the same chat again in the same form is a no-op, not a conflict.
    db.bind_telegram_chat(_A, 1001)
    assert db.get_athlete_account(_A)["telegram_chat_id"] == "1001"


@pytest.mark.parametrize(("legacy", "reason"), [("01001", "canonical"), ("+1002", "canonical"), ("1", "owner")])
def test_a_legacy_chat_is_not_run_and_named_in_the_readiness(db, monkeypatch, legacy: str, reason: str) -> None:
    from titan import worker
    from titan.core.athlete import CONSENT_TEXT_VERSION

    monkeypatch.setattr(worker, "_utc_now", lambda: _NOW)
    _add(db, _A, "1002", monkeypatch)
    db.bind_garmin_account(_A, "garmin-a")
    db.set_garmin_token_state(_A, "ok")
    db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_NOW)
    assert worker._readiness_problem(db, _A) is None
    _store_legacy_chat(db, _A, legacy)
    problem = worker._readiness_problem(db, _A)
    assert problem is not None and "telegram" in problem and reason in problem


def test_an_athletes_bot_refuses_a_chat_not_in_canonical_form(monkeypatch) -> None:
    from titan.integrations.telegram_bot import TitanTelegramBot

    _settings(monkeypatch)
    with pytest.raises(ValueError):
        TitanTelegramBot(chat_id="01001", athlete_id=_B)
    assert TitanTelegramBot(chat_id="1001", athlete_id=_A).chat_id == 1001


def test_the_owners_chat_is_trusted_in_the_form_telegram_reports_it(monkeypatch) -> None:
    from titan.integrations.telegram_bot import TitanTelegramBot

    _settings(monkeypatch, owner_chat=" 01 ")
    bot = TitanTelegramBot()
    assert bot._is_trusted(1)
    assert not bot._is_trusted(1001)
    # Not a chat id at all: nobody is trusted (fail closed, INV-16).
    _settings(monkeypatch, owner_chat="+1")
    assert not TitanTelegramBot()._is_trusted(1)


# ── RC-04: no binding without the owner's chat ───────────────────────────────


@pytest.mark.parametrize("owner_chat", ["", "   "])
def test_no_chat_is_bound_while_telegram_chat_id_is_empty(db, monkeypatch, owner_chat: str) -> None:
    _settings(monkeypatch, owner_chat=owner_chat)
    with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
        _add(db, _A, "1001", monkeypatch)
    assert not lifecycle.athlete_exists(db, _A)
    with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
        db.bind_telegram_chat(_A, "1001")


# ── RC-03: no bot is not a delivery ──────────────────────────────────────────


def test_send_message_without_a_bot_is_not_delivered(monkeypatch) -> None:
    from titan.integrations.telegram_bot import TitanTelegramBot

    _settings(monkeypatch)
    bot = TitanTelegramBot()
    assert bot.bot is None
    assert bot.send_message("hello") is False
    assert bot.send_alert(title="t", message="m") is False


def test_without_a_bot_the_owners_day_is_not_recorded_delivered(db, monkeypatch) -> None:
    from titan import worker

    monkeypatch.setattr(worker, "_utc_now", lambda: _NOW)
    day = _NOW.date().isoformat()
    monkeypatch.setattr(
        db, "get_governance_decision_on",
        lambda _athlete, _day: {"session_post_governance": "EASY", "locks_applied": []},
    )
    attempt = worker._claim_routine(db, "owner", _NOW)
    assert attempt == 1
    assert worker._attempt_morning(db, "owner", day, attempt) is False
    delivered = db.conn.execute(
        "SELECT delivered_at FROM worker_routine_executions WHERE athlete_id = 'owner' "
        "AND execution_date = ? AND routine_type = ?", (day, worker.ROUTINE_MORNING),
    ).fetchone()[0]
    assert delivered is None
    # The day is tried again, and after the last attempt left without a crash or a loop.
    for _ in range(worker.ROUTINE_MAX_ATTEMPTS - 1):
        attempt = worker._claim_routine(db, "owner", _NOW)
        assert isinstance(attempt, int)
        assert worker._attempt_morning(db, "owner", day, attempt) is False
    assert worker._claim_routine(db, "owner", _NOW) is False


# ── RC-02: operator alerts about an athlete reach Zaf ────────────────────────


class _Recorder:
    """Stands in for TitanTelegramBot: records the chat and the text of every send."""

    sent: list[tuple[str, str]] = []

    def __init__(self, *_args, chat_id=None, db=None, athlete_id: str = "owner", **_kwargs) -> None:
        self.athlete_id = athlete_id
        self.db = db
        self.chat = str(chat_id) if chat_id is not None else _OWNER_CHAT

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        type(self).sent.append((self.chat, text))
        return True

    def send_alert(self, title: str, message: str, level: str = "warning") -> bool:
        return self.send_message(f"{title}\n{message}")

    def send_structured_alert(self, event_type: str, lock_code: str, message: str) -> bool:
        return self.send_message(f"{event_type}/{lock_code}\n{message}")


def _degraded_alert(telegram: _Recorder) -> None:
    from titan.orchestration.effect_bus import TitanEffectBus

    tracker = SimpleNamespace(update=lambda flags, alert_fn: alert_fn(
        "TITAN degraded for >25h — garmin_data_stale unresolved. Check credentials/connectivity."
    ))
    hook = TitanEffectBus.make_degraded_hook(tracker, SimpleNamespace(), telegram)
    hook(SimpleNamespace(decision_trace={}))


def test_an_operator_alert_about_an_athlete_reaches_zaf_with_the_athlete_id(monkeypatch) -> None:
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Recorder)
    _Recorder.sent = []
    _degraded_alert(_Recorder(chat_id="1001", athlete_id=_A))
    to_athlete = [text for chat, text in _Recorder.sent if chat == "1001"]
    to_owner = [text for chat, text in _Recorder.sent if chat == _OWNER_CHAT]
    assert len(to_athlete) == 1 and len(to_owner) == 1
    assert "Check credentials" not in to_athlete[0] and "garmin_data_stale" not in to_athlete[0]
    assert _A in to_owner[0] and "Check credentials/connectivity" in to_owner[0]


def test_the_owners_operator_alert_is_unchanged(monkeypatch) -> None:
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Recorder)
    _Recorder.sent = []
    _degraded_alert(_Recorder())
    assert _Recorder.sent == [(
        _OWNER_CHAT,
        "TITAN degraded mode\nTITAN degraded for >25h — garmin_data_stale unresolved. Check credentials/connectivity.",
    )]


def test_the_stale_garmin_alert_of_an_athlete_reaches_zaf(monkeypatch) -> None:
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Recorder)
    _Recorder.sent = []
    telegram_bot.alert_operator(
        _Recorder(chat_id="1001", athlete_id=_A), title="Garmin data stale", event_type="garmin_data_stale",
        lock_code="GARMIN_DATA_STALE", message="Garmin data is stale.", level="critical",
        athlete_text="Your Garmin data has not synced.",
    )
    assert _Recorder.sent[0] == ("1001", "Your Garmin data has not synced.")
    assert _Recorder.sent[1][0] == _OWNER_CHAT and _A in _Recorder.sent[1][1]


# ── RC-01 end to end: the worker's real morning round ────────────────────────


@pytest.mark.slow
@pytest.mark.integration
def test_a_worker_morning_sends_each_athlete_only_to_its_own_chat(tmp_path, monkeypatch) -> None:
    """A at "1001"; B stored before D-107 as "01001", which is int 1001: A's chat.

    Before D-107 B was run and B's morning went to A's chat. Now B is not run, Zaf is
    told, and every message goes only to the chat of the athlete it is about.
    """
    from cryptography.fernet import Fernet
    from freezegun import freeze_time

    from tests.synthetic import pilot
    from tests.synthetic.pilot import ATHLETE_A, ATHLETE_B
    from titan import worker
    from titan.config.settings import get_settings
    from titan.core.athlete import CONSENT_TEXT_VERSION
    from titan.integrations.garmin_sync import relogin_athlete

    data = tmp_path / "data"
    data.mkdir()
    key = tmp_path / "athletes.key"
    key.write_bytes(Fernet.generate_key())
    os.chmod(key, 0o600)
    record = tmp_path / "record.jsonl"
    for name, value in {
        "TITAN_DATA_DIR": str(data), "TITAN_TOKEN_KEY_FILE": str(key),
        pilot.RECORD_ENV: str(record), "TITAN_PILOT_ATHLETE": "scheduler",
        "GARMIN_EMAIL": pilot.OWNER_EMAIL, "GARMIN_PASSWORD": "placeholder",
        "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": pilot.OWNER_CHAT,
        "WEATHER_LOCATION": "Athens,GR", "TITAN_MULTI_ATHLETE": "1", **pilot.OWNER.profile.env(),
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    pilot.install_fakes(monkeypatch)

    evening = datetime.combine(pilot.FIRST_MORNING, datetime.min.time(), UTC) - timedelta(hours=6)
    with freeze_time(evening):
        db = DatabaseManager(db_dir=data)
        for i, athlete in enumerate((ATHLETE_A, ATHLETE_B)):
            monkeypatch.setattr(lifecycle, "new_athlete_id", lambda a=athlete: a.athlete_id)
            lifecycle.add_athlete(db, athlete.key, pilot.athlete_profile_record(athlete), athlete.chat,
                                  now=evening + timedelta(minutes=i))
            relogin_athlete(db, athlete.athlete_id, athlete.garmin_account, "placeholder", lambda: "")
            assert db.grant_consent(athlete.athlete_id, CONSENT_TEXT_VERSION, now=evening + timedelta(minutes=i))
    _store_legacy_chat(db, ATHLETE_B.athlete_id, "01001")

    monkeypatch.setattr(worker, "_CHILD_ENTRY", pilot.child_entry)
    at = datetime.combine(pilot.FIRST_MORNING, datetime.min.time(), UTC) + timedelta(hours=7, seconds=30)
    monkeypatch.setattr(worker, "_utc_now", lambda: at)
    try:
        worker._morning_round(db)
    finally:
        db.close()
        get_settings.cache_clear()

    sends = [r for r in pilot.read_records(record) if r["kind"] == "telegram"]
    own_chat = {"owner": pilot.OWNER_CHAT, ATHLETE_A.athlete_id: ATHLETE_A.chat, "scheduler": pilot.OWNER_CHAT}
    assert sends, "nothing was sent at all"
    assert not [r for r in sends if r["process_athlete"] == ATHLETE_B.athlete_id], "B was run"
    for r in sends:
        assert r["chat"] == own_chat[r["process_athlete"]], r
    assert any(r["process_athlete"] == ATHLETE_A.athlete_id and r["chat"] == ATHLETE_A.chat for r in sends)
    notices = [r["text"] for r in sends if r["process_athlete"] == "scheduler"]
    assert any(ATHLETE_B.athlete_id in t and "canonical" in t for t in notices), notices
    with sqlite3.connect(data / "titan_core.db") as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM worker_routine_executions WHERE athlete_id = ?", (ATHLETE_B.athlete_id,)
        ).fetchone()[0] == 0
