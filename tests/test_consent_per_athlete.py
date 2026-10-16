"""Phase 4 step 7: consent per athlete (ADR-0067 D4; D-096).

- The athlete agrees in their own chat to one numbered text version (docs/consent/).
- Without a current consent nothing is called or written for them.
- /stop revokes; the routine then does not start. A new consent within the 30 days takes
  effect from the next UTC day. The owner is exempt.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from titan.core.athlete import (
    CONSENT_FREEZE_DAYS,
    CONSENT_TEXT_VERSION,
    AthleteNotReady,
    consent_is_current,
)
from titan.core.database import DatabaseManager
from titan.integrations.telegram_bot import (
    _AUDIT_UNAVAILABLE_REPLY,
    _NO_CONSENT_REPLY,
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
_REPO = Path(__file__).resolve().parents[1]
_DAY1 = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)


def _row(version: str, granted: str, revoked: str | None = None) -> dict:
    return {"text_version": version, "granted_at": granted, "revoked_at": revoked}


# ── The rule ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_a_first_consent_counts_from_its_own_day() -> None:
    rows = [_row(CONSENT_TEXT_VERSION, "2026-10-15T06:00:00+00:00")]

    assert consent_is_current(rows, date(2026, 10, 15))
    assert not consent_is_current(rows, date(2026, 10, 14))


@pytest.mark.unit
@pytest.mark.parametrize("rows", [
    [],
    [_row("v0", "2026-10-01T06:00:00+00:00")],
    [_row(CONSENT_TEXT_VERSION, "2026-10-01T06:00:00+00:00", "2026-10-10T06:00:00+00:00")],
])
def test_no_row_an_old_version_or_a_revoked_row_is_not_consent(rows) -> None:
    assert not consent_is_current(rows, date(2026, 10, 15))


@pytest.mark.unit
def test_a_consent_after_stop_counts_from_the_next_utc_day() -> None:
    rows = [
        _row(CONSENT_TEXT_VERSION, "2026-10-01T06:00:00+00:00", "2026-10-15T07:00:00+00:00"),
        _row(CONSENT_TEXT_VERSION, "2026-10-15T20:00:00+00:00"),
    ]

    assert not consent_is_current(rows, date(2026, 10, 15))
    assert consent_is_current(rows, date(2026, 10, 16))


# ── The database ──────────────────────────────────────────────────────────────


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER_CHAT))
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
    for athlete, chat in ((_A, CHAT_A), (_B, CHAT_B)):
        manager.save_athlete_profile(athlete, _PROFILE)
        manager.bind_garmin_account(athlete, f"garmin-{athlete}")
        manager.set_garmin_token_state(athlete, "ok")
        manager.bind_telegram_chat(athlete, chat)
    yield manager
    manager.close()


def _consents(db: DatabaseManager) -> list[tuple]:
    rows = db.conn.execute(
        "SELECT athlete_id, consent_type, text_version, channel, revoked_at IS NULL FROM consent_log ORDER BY id"
    )
    return [tuple(r) for r in rows.fetchall()]


@pytest.mark.integration
def test_a_grant_is_one_telegram_row_for_the_current_version(db) -> None:
    assert db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_DAY1) is True
    assert db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_DAY1) is False

    assert _consents(db) == [(_A, "coaching", CONSENT_TEXT_VERSION, "telegram", 1)]
    assert db.has_current_consent(_A, now=_DAY1)
    assert not db.has_current_consent(_B, now=_DAY1)


@pytest.mark.integration
def test_no_consent_for_the_owner_or_for_another_version(db) -> None:
    with pytest.raises(ValueError, match="owner"):
        db.grant_consent("owner", CONSENT_TEXT_VERSION)
    with pytest.raises(ValueError, match="current consent text"):
        db.grant_consent(_A, "v0")

    assert _consents(db) == []
    assert db.has_current_consent("owner")


@pytest.mark.integration
def test_a_new_consent_is_refused_once_the_30_days_after_stop_have_passed(db) -> None:
    db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_DAY1)
    db.conn.execute("UPDATE consent_log SET revoked_at = ? WHERE athlete_id = ?", (_DAY1.isoformat(), _A))
    db.conn.commit()

    with pytest.raises(ValueError, match="30 days"):
        db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_DAY1 + timedelta(days=CONSENT_FREEZE_DAYS, hours=1))
    assert db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_DAY1 + timedelta(days=CONSENT_FREEZE_DAYS)) is True


# ── The worker ────────────────────────────────────────────────────────────────


def _forbid_collaborators(monkeypatch) -> None:
    from titan.core import athlete
    from titan.integrations import garmin_sync, telegram_bot, weather_api

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("touched an athlete who has no consent")

    for module, name in (
        (garmin_sync, "GarminSync"), (weather_api, "WeatherAPI"), (telegram_bot, "TitanTelegramBot"),
        (athlete, "load_athlete_profile"),
    ):
        monkeypatch.setattr(module, name, _forbidden)


@pytest.mark.integration
def test_without_consent_the_worker_builds_calls_and_writes_nothing(db, monkeypatch) -> None:
    from titan import worker

    _forbid_collaborators(monkeypatch)
    writes = db.conn.total_changes

    with pytest.raises(AthleteNotReady, match="consent"):
        worker._build_daily_coach(db, athlete_id=_A)
    assert worker.sync_athlete_on_request(db, _A).startswith("⏸")
    assert db.conn.total_changes == writes


@pytest.mark.integration
def test_after_stop_the_routine_does_not_start(db, monkeypatch) -> None:
    from titan import worker

    db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_DAY1 - timedelta(days=3))
    db.revoke_consent(_A)
    monkeypatch.setattr(worker, "_utc_now", lambda: _DAY1)
    monkeypatch.setattr(worker, "_run_attempt", lambda *_a: pytest.fail("the routine started after /stop"))

    worker._scheduled_morning(db, _A)

    # Nothing for the athlete; the only row is the owner's marker of Zaf's notice (D-099).
    assert db.conn.execute(
        "SELECT athlete_id, routine_type FROM worker_routine_executions"
    ).fetchall() == [("owner", f"not_ready:{_A}")]


@pytest.mark.integration
def test_a_new_consent_after_stop_resumes_the_next_utc_day(db, monkeypatch) -> None:
    from titan import worker

    db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_DAY1 - timedelta(days=3))
    db.conn.execute("UPDATE consent_log SET revoked_at = ? WHERE athlete_id = ?", (_DAY1.isoformat(), _A))
    db.conn.commit()
    db.grant_consent(_A, CONSENT_TEXT_VERSION, now=_DAY1 + timedelta(hours=1))
    ran: list[str] = []
    monkeypatch.setattr(worker, "_run_attempt", worker._attempt_morning)
    monkeypatch.setattr(worker, "_run_morning", lambda _db, athlete_id: ran.append(athlete_id))

    monkeypatch.setattr(worker, "_utc_now", lambda: _DAY1 + timedelta(hours=2))
    worker._scheduled_morning(db, _A)
    assert ran == []

    monkeypatch.setattr(worker, "_utc_now", lambda: _DAY1 + timedelta(days=1))
    worker._scheduled_morning(db, _A)
    assert ran == [_A]


@pytest.mark.integration
def test_the_owner_runs_without_any_consent_row(db, monkeypatch) -> None:
    from titan import worker

    ran: list[str] = []
    monkeypatch.setattr(worker, "_utc_now", lambda: _DAY1)
    monkeypatch.setattr(worker, "_run_attempt", worker._attempt_morning)
    monkeypatch.setattr(worker, "_run_morning", lambda _db, athlete_id: ran.append(athlete_id))

    worker._scheduled_morning(db, "owner")

    assert ran == ["owner"]
    assert _consents(db) == []


# ── Telegram ──────────────────────────────────────────────────────────────────


class _FakeTeleBot:
    def __init__(self) -> None:
        self.handlers: dict = {}
        self.replies: list[tuple[int, str, dict]] = []

    def message_handler(self, commands=None, func=None):  # noqa: ANN001, ANN201
        def decorator(fn):  # noqa: ANN001, ANN202
            for command in commands or []:
                self.handlers[command] = fn
            return fn

        return decorator

    def callback_query_handler(self, func=None):  # noqa: ANN001, ANN201
        return lambda fn: fn

    def reply_to(self, message, text: str, **kwargs) -> None:  # noqa: ANN001
        self.replies.append((message.chat.id, text, kwargs))


@pytest.fixture
def bot(db):
    owner_bot = TitanTelegramBot(bot_token="", db=db)
    owner_bot.bot = _FakeTeleBot()
    owner_bot._register_handlers()
    return owner_bot


def _send(bot: TitanTelegramBot, text: str, chat_id: int) -> list[str]:
    before = len(bot.bot.replies)
    command = text.split()[0].lstrip("/")
    bot.bot.handlers[command](SimpleNamespace(chat=SimpleNamespace(id=chat_id), text=text))
    return [reply for _chat, reply, _kw in bot.bot.replies[before:]]


def _audit(db: DatabaseManager) -> list[tuple[str, str, str, str]]:
    return [
        (r["coach_id"], r["athlete_id"], r["action_type"], r.get("action_detail") or "")
        for r in reversed(db.get_coach_audit_log())
    ]


@pytest.mark.integration
def test_consent_shows_the_current_text_in_plain_text(bot) -> None:
    (text,) = _send(bot, "/consent", CHAT_A)

    expected = (_REPO / "docs" / "consent" / f"{CONSENT_TEXT_VERSION}.md").read_text(encoding="utf-8").strip()
    assert text.startswith(expected)
    assert text.endswith(f"/agree {CONSENT_TEXT_VERSION}")
    assert bot.bot.replies[-1][2] == {"parse_mode": ""}


@pytest.mark.integration
def test_agree_audits_first_then_records_that_athletes_consent(bot, db) -> None:
    (text,) = _send(bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_A)

    assert text.startswith("✅")
    assert _audit(db) == [(f"telegram:{CHAT_A}", _A, "TELEGRAM_CONSENT", CONSENT_TEXT_VERSION)]
    assert _consents(db) == [(_A, "coaching", CONSENT_TEXT_VERSION, "telegram", 1)]


@pytest.mark.integration
@pytest.mark.parametrize("text", ["/agree", "/agree v0", "/agree yes"])
def test_agree_needs_the_current_version_by_name(bot, db, text) -> None:
    (reply,) = _send(bot, text, CHAT_A)

    assert "/consent" in reply
    assert _audit(db) == [] and _consents(db) == []


@pytest.mark.integration
def test_agree_without_its_audit_row_records_nothing(bot, db, monkeypatch) -> None:
    monkeypatch.setattr(db, "log_coach_action", MagicMock(side_effect=RuntimeError("disk full")))
    monkeypatch.setattr(
        "titan.observability.metrics.get_metrics", lambda: SimpleNamespace(counter=lambda *a, **k: None)
    )

    assert _send(bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_A) == [_AUDIT_UNAVAILABLE_REPLY]
    assert _consents(db) == []


@pytest.mark.integration
def test_agree_without_the_text_records_nothing(bot, db, monkeypatch) -> None:
    from titan.integrations import telegram_bot

    monkeypatch.setattr(telegram_bot, "_CONSENT_DIR", Path("/nonexistent"))

    (reply,) = _send(bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_A)

    assert reply.startswith("❌")
    assert _audit(db) == [] and _consents(db) == []


@pytest.mark.integration
@pytest.mark.parametrize("chat", [STRANGER, OWNER_CHAT])
def test_neither_a_stranger_nor_the_owner_can_agree(bot, db, chat) -> None:
    replies = _send(bot, f"/agree {CONSENT_TEXT_VERSION}", chat)

    assert replies == ([] if chat == STRANGER else ["ℹ️ The owner is exempt from consent."])
    assert _audit(db) == [] and _consents(db) == []


@pytest.mark.integration
def test_sync_without_consent_writes_nothing(bot, db) -> None:
    bot.register_athlete_command("sync", lambda athlete_id: pytest.fail("synced without consent"))

    assert _send(bot, "/sync", CHAT_A) == [_NO_CONSENT_REPLY]
    assert _audit(db) == []


@pytest.mark.integration
def test_agree_then_stop_from_the_chat(bot, db) -> None:
    _send(bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_A)
    _send(bot, f"/agree {CONSENT_TEXT_VERSION}", CHAT_B)
    assert db.has_current_consent(_A)

    _send(bot, "/stop", CHAT_A)

    assert not db.has_current_consent(_A)
    assert db.has_current_consent(_B)


# ── The text itself ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_the_current_text_exists_fits_one_message_and_ships_in_the_image() -> None:
    text = (_REPO / "docs" / "consent" / f"{CONSENT_TEXT_VERSION}.md").read_text(encoding="utf-8")

    assert f"έκδοση {CONSENT_TEXT_VERSION}" in text
    assert "ΠΡΟΣΧΕΔΙΟ" in text  # until a lawyer has reviewed it (ADR-0067 D4.1)
    assert len(text) + 100 < 4096  # one Telegram message, with the /agree line
    dockerignore = (_REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert dockerignore.index("!docs/consent/") > dockerignore.index("docs/")
