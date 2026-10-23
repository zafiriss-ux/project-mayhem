"""OW-F3, second part (ADR-0069 §3): /injury opens an injury, /injury off closes it.

While an injury is open, H1 triggers and the morning is REST. A day with no declared injury
does not change: H1 stays UNKNOWN (D-134). If the injury cannot be read, H1 triggers: a
failure is closed, never open. Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_daily_coach_characterization import (  # noqa: F401  (world is a fixture)
    _run_scenario,
    normal_day,
    world,
)
from titan.core.database import DatabaseManager
from titan.integrations.telegram_bot import TitanTelegramBot
from titan.science.governance_engine import GovernanceEngine


@pytest.fixture
def db(tmp_path: Path):
    d = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    yield d
    d.close()


@pytest.fixture
def bot(db):
    return TitanTelegramBot(bot_token="", chat_id="12345", db=db)


# ── Storage ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_an_injury_opens_and_closes(db):
    assert db.get_open_injury(athlete_id="owner") is None
    assert db.open_injury(athlete_id="owner", description="sore knee", opened_at="2026-03-02T08:00:00+00:00")
    assert db.get_open_injury(athlete_id="owner")["description"] == "sore knee"
    assert db.close_injury(athlete_id="owner", closed_at="2026-03-05T08:00:00+00:00")
    assert db.get_open_injury(athlete_id="owner") is None
    assert db.close_injury(athlete_id="owner", closed_at="2026-03-06T08:00:00+00:00") is False


@pytest.mark.unit
def test_a_second_injury_keeps_the_open_one(db):
    assert db.open_injury(athlete_id="owner", description="sore knee", opened_at="2026-03-02T08:00:00+00:00")
    assert db.open_injury(athlete_id="owner", description="calf", opened_at="2026-03-03T08:00:00+00:00") is False
    assert db.get_open_injury(athlete_id="owner")["description"] == "sore knee"


@pytest.mark.unit
def test_an_injury_belongs_to_one_athlete(db):
    assert db.open_injury(athlete_id="a1", description="ankle", opened_at="2026-03-02T08:00:00+00:00")
    assert db.get_open_injury(athlete_id="owner") is None


# ── Telegram ─────────────────────────────────────────────────────────────────

def _actions(db) -> list[str]:
    return [row["action_type"] for row in db.get_coach_audit_log()]


@pytest.mark.unit
def test_injury_command_opens_and_closes_with_audit(bot, db):
    reply = bot.handle_injury_text("sore left knee", chat_id="12345")
    assert "sore left knee" in reply
    assert db.get_open_injury(athlete_id="owner")["description"] == "sore left knee"
    reply = bot.handle_injury_text("off", chat_id="12345")
    assert db.get_open_injury(athlete_id="owner") is None
    assert "closed" in reply.lower()
    assert _actions(db).count("TELEGRAM_INJURY_OPEN") == 1
    assert _actions(db).count("TELEGRAM_INJURY_CLOSE") == 1


@pytest.mark.unit
def test_injury_without_text_shows_the_state(bot, db):
    assert "Usage" in bot.handle_injury_text("", chat_id="12345")
    bot.handle_injury_text("calf", chat_id="12345")
    assert "calf" in bot.handle_injury_text("", chat_id="12345")


@pytest.mark.unit
def test_injury_off_with_none_open(bot, db):
    assert "no open injury" in bot.handle_injury_text("off", chat_id="12345").lower()


@pytest.mark.unit
def test_injury_is_not_opened_when_the_audit_fails(bot, db, monkeypatch):
    def _fail(**_kwargs):
        raise RuntimeError("audit down (synthetic)")

    monkeypatch.setattr(db, "log_coach_action", _fail)
    bot.handle_injury_text("sore knee", chat_id="12345")
    assert db.get_open_injury(athlete_id="owner") is None


# ── Morning ──────────────────────────────────────────────────────────────────

def _spy(monkeypatch) -> list[dict]:
    seen: list[dict] = []
    original = GovernanceEngine._build_decision_rationale

    def spy(self, context, session_plan, applied_locks):
        rationale = original(self, context, session_plan, applied_locks)
        seen.append({f.gate: f.status for f in rationale.gate_findings})
        return rationale

    monkeypatch.setattr(GovernanceEngine, "_build_decision_rationale", spy)
    return seen


def test_an_open_injury_makes_the_morning_rest(world, monkeypatch):
    seen = _spy(monkeypatch)

    def _injured(index, db):
        db.open_injury(athlete_id="owner", description="sore knee", opened_at="2026-01-01T00:00:00+00:00")

    days = _run_scenario(world, [normal_day(0)], soreness=1, before_morning=_injured)["days"]
    assert seen[-1]["H1"] == "TRIGGERED"
    assert any("*Today:* REST" in text for text in days[-1]["telegram"])


def test_a_closed_injury_leaves_h1_unknown(world, monkeypatch):
    seen = _spy(monkeypatch)

    def _healed(index, db):
        db.open_injury(athlete_id="owner", description="sore knee", opened_at="2026-01-01T00:00:00+00:00")
        db.close_injury(athlete_id="owner", closed_at="2026-01-02T00:00:00+00:00")

    _run_scenario(world, [normal_day(0)], soreness=1, before_morning=_healed)
    assert seen[-1]["H1"] == "UNKNOWN"


def test_an_unreadable_injury_store_triggers_h1(world, monkeypatch):
    seen = _spy(monkeypatch)

    def _broken(index, db):
        def _fail(**_kwargs):
            raise RuntimeError("disk I/O error (synthetic)")

        world["monkeypatch"].setattr(db, "get_open_injury", _fail)

    _run_scenario(world, [normal_day(0)], soreness=1, before_morning=_broken)
    assert seen[-1]["H1"] == "TRIGGERED"
