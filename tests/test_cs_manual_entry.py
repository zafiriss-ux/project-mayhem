"""Manual time-trial entry for Critical Speed (D-039): parser, Telegram /time_trial, console option."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

from titan.core.database import DatabaseManager
from titan.integrations.telegram_bot import TitanTelegramBot
from titan.science.critical_speed import parse_time_trial, parse_trial_date
from titan.ui import menu_system


@pytest.fixture
def db(tmp_path):
    d = DatabaseManager(db_name="test_cs_manual.db", db_dir=tmp_path)
    yield d
    d.close()


@pytest.fixture
def bot(db):
    return TitanTelegramBot(bot_token="", chat_id="12345", db=db)


# ── Parser ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("distance", "time", "expected"),
    [
        ("5000", "18:30", (5000.0, 1110.0)),
        ("5000m", "1110", (5000.0, 1110.0)),
        ("5k", "18:30", (5000.0, 1110.0)),
        ("3,2km", "11:00", (3200.0, 660.0)),
        ("21.0975km", "1:25:00", (21097.5, 5100.0)),
    ],
)
def test_parse_time_trial_accepts_common_forms(distance, time, expected):
    assert parse_time_trial(distance, time) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("distance", "time", "message"),
    [
        ("five", "18:30", "Invalid distance"),
        ("5000", "18:75", "Invalid time"),
        ("5000", "1:2:3:4", "Invalid time"),
        ("5000", "-18:30", "Invalid time"),
        ("200", "0:59", "Distance out of range"),
        ("50k", "4:00:00", "Distance out of range"),
        ("5000", "0:30", "Time out of range"),
        ("5000", "7:00:00", "Time out of range"),
        ("5000", "8:00", "Average speed not plausible"),   # 10.4 m/s
        ("1000", "20:00", "Average speed not plausible"),  # 0.83 m/s
        ("nan", "18:30", "Distance out of range"),
    ],
)
def test_parse_time_trial_rejects_bad_input(distance, time, message):
    with pytest.raises(ValueError, match=message):
        parse_time_trial(distance, time)


def test_parse_trial_date():
    today = date(2026, 10, 10)
    assert parse_trial_date(None, today) == "2026-10-10"
    assert parse_trial_date("  ", today) == "2026-10-10"
    assert parse_trial_date("2026-10-01", today) == "2026-10-01"
    with pytest.raises(ValueError, match="future"):
        parse_trial_date("2026-10-11", today)
    with pytest.raises(ValueError, match="Invalid date"):
        parse_trial_date("10/10/2026", today)


# ── Telegram /time_trial ─────────────────────────────────────────────────────

@pytest.mark.integration
def test_time_trial_stores_performance_and_audit_row(bot, db):
    reply = bot.handle_time_trial_text("5000 18:30 2026-10-01", chat_id=12345)
    assert reply.startswith("✅")
    assert "5000 m in 18:30 on 2026-10-01" in reply
    assert db.get_cs_performances(athlete_id="owner") == [("2026-10-01", 5000.0, 1110.0)]
    with db._lock:
        rows = db.conn.execute(
            "SELECT action_type, athlete_id FROM coach_audit_log"
        ).fetchall()
    assert ("TELEGRAM_TIME_TRIAL", "owner") in [tuple(r) for r in rows]


@pytest.mark.integration
def test_time_trial_defaults_to_today(bot, db):
    reply = bot.handle_time_trial_text("3k 10:00")
    today = datetime.now(UTC).date().isoformat()
    assert reply.startswith("✅")
    assert db.get_cs_performances() == [(today, 3000.0, 600.0)]


@pytest.mark.parametrize("args", ["", "5000", "5000 18:30 2026-10-01 extra"])
def test_time_trial_wrong_arity_returns_usage(bot, db, args):
    assert bot.handle_time_trial_text(args).startswith("Usage: /time_trial")
    assert db.get_cs_performances() == []


def test_time_trial_invalid_input_writes_nothing(bot, db):
    reply = bot.handle_time_trial_text("5000 8:00")
    assert reply.startswith("❌ Average speed not plausible")
    assert db.get_cs_performances() == []


def test_time_trial_without_db():
    bot = TitanTelegramBot(bot_token="", chat_id="12345", db=None)
    assert bot.handle_time_trial_text("5000 18:30") == "❌ Database not available."


def test_time_trial_rejected_when_audit_fails():
    fake_db = MagicMock()
    fake_db.log_coach_action.side_effect = RuntimeError("disk full")
    bot = TitanTelegramBot(bot_token="", chat_id="12345", db=fake_db)
    reply = bot.handle_time_trial_text("5000 18:30")
    assert reply.startswith("❌ Audit log unavailable")
    fake_db.log_cs_performance.assert_not_called()


# ── Console option ───────────────────────────────────────────────────────────

@pytest.mark.integration
def test_console_records_time_trial(db, capsys):
    answers = iter(["10k", "40:00", "2026-09-20", ""])
    with patch("builtins.input", lambda *_: next(answers)):
        menu_system._record_time_trial({"db": db})
    assert db.get_cs_performances() == [("2026-09-20", 10000.0, 2400.0)]
    assert "✅" in capsys.readouterr().out


def test_console_rejects_bad_time_trial(db, capsys):
    answers = iter(["5000", "abc", "", ""])
    with patch("builtins.input", lambda *_: next(answers)):
        menu_system._record_time_trial({"db": db})
    assert db.get_cs_performances() == []
    assert "Invalid time" in capsys.readouterr().out


def test_console_without_db(capsys):
    with patch("builtins.input", return_value=""):
        menu_system._record_time_trial({})
    assert "❌" in capsys.readouterr().out


def test_data_browser_routes_option_7(db):
    answers = iter(["7", "5k", "18:30", "", "", "0"])
    with patch("builtins.input", lambda *_: next(answers)):
        menu_system.menu_data_browser({"db": db})
    assert len(db.get_cs_performances()) == 1
