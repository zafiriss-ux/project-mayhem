import pytest

from titan.integrations.telegram_bot import TitanTelegramBot


@pytest.mark.integration
def test_send_daily_coaching_includes_rationale_lines(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=None)
    captured = {}
    def _capture(text):
        captured["text"] = text
        return True
    monkeypatch.setattr(bot, "send_message", _capture)

    ok = bot.send_daily_coaching(
        {
            "session_type": "EASY",
            "duration": "8 km",
            "optimal_time": "06:30",
            "dew_point": 9,
            "conditions": "Clear",
            "hrv_status": "stable",
            "sleep_quality": 80,
            "readiness_score": 75,
            "nutrition_plan": "250g carbs",
            "primary_reason": "TSB below threshold.",
            "actionable_guidance": "Run easy today.",
        }
    )

    assert ok is True
    assert "Why this decision" in captured["text"]
    assert "Actionable guidance" in captured["text"]


@pytest.mark.integration
def test_send_daily_coaching_omits_rationale_when_missing(monkeypatch):
    bot = TitanTelegramBot(bot_token="", chat_id=None)
    captured = {}
    def _capture(text):
        captured["text"] = text
        return True
    monkeypatch.setattr(bot, "send_message", _capture)

    ok = bot.send_daily_coaching({})

    assert ok is True
    assert "Why this decision" not in captured["text"]
    assert "Actionable guidance" not in captured["text"]
