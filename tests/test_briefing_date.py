"""OW-L5 14α (D-130): the briefing is dated with the morning's day, not the clock's.

A morning claimed for one day and sent after midnight (D-109) said the next day's date
at the top of the message. The send step now hands the claimed day to the bot.
Synthetic data only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from titan.integrations import telegram_bot as tg
from titan.integrations.telegram_bot import TitanTelegramBot


def _coaching(**extra) -> dict:
    return {
        "session_type": "EASY", "duration": "8 km", "optimal_time": "07:00", "dew_point": 10,
        "conditions": "GOOD", "hrv_status": "STABLE", "sleep_quality": 80, "readiness_score": 70,
        "nutrition_plan": "250g carbs", "shoe": "Daily trainer", **extra,
    }


@pytest.fixture
def bot():
    b = TitanTelegramBot(bot_token="", chat_id="12345")
    b.sent = []
    b.send_message = lambda text, **kw: b.sent.append(text) or True
    return b


class _AfterMidnight(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ANN001, ANN206
        return datetime(2026, 10, 15, 0, 1, tzinfo=UTC)


def test_the_briefing_carries_the_day_it_was_given(bot, monkeypatch):
    monkeypatch.setattr(tg, "datetime", _AfterMidnight)
    bot.send_daily_coaching(_coaching(briefing_date="2026-10-14"))
    assert "\nWednesday, October 14, 2026\n" in bot.sent[0]


def test_without_a_day_the_briefing_keeps_todays_date(bot, monkeypatch):
    monkeypatch.setattr(tg, "datetime", _AfterMidnight)
    bot.send_daily_coaching(_coaching())
    assert "\nThursday, October 15, 2026\n" in bot.sent[0]


def test_a_malformed_day_falls_back_to_today(bot, monkeypatch):
    monkeypatch.setattr(tg, "datetime", _AfterMidnight)
    bot.send_daily_coaching(_coaching(briefing_date="2026-02-31"))
    assert "\nThursday, October 15, 2026\n" in bot.sent[0]


def test_the_send_step_hands_the_claimed_day_to_the_bot():
    from titan.orchestration.daily_coach import DailyCoach

    sent: list[dict] = []

    class _Telegram:
        def send_daily_coaching(self, payload: dict) -> bool:
            sent.append(payload)
            return True

    class _Result:
        coaching_payload: dict = _coaching()

    coach = DailyCoach.__new__(DailyCoach)
    coach.telegram = _Telegram()
    coach.routine_date = "2026-10-14"
    coach.briefing_note = None

    assert coach._make_send_telegram_handler()(None, _Result()) is True
    assert sent[0]["briefing_date"] == "2026-10-14"
    assert "briefing_date" not in _Result.coaching_payload  # the decision's payload is not changed
