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


@pytest.mark.integration
def test_send_daily_coaching_rounds_float_noise_in_the_rationale(monkeypatch):
    """SV-07: '19.699999999999996 vs 15.0' reached the athlete's phone."""
    bot = TitanTelegramBot(bot_token="", chat_id=None)
    captured = {}
    monkeypatch.setattr(bot, "send_message", lambda text: captured.setdefault("text", text) or True)

    bot.send_daily_coaching(
        {
            "primary_reason": "HRV collapse crossed safety threshold (19.699999999999996 vs 15.0, margin 4.7).",
            "actionable_guidance": "RHR 10.100000000000001 above baseline.",
        }
    )

    assert "(19.7 vs 15.0, margin 4.7)" in captured["text"]
    assert "RHR 10.1 above baseline" in captured["text"]
    assert "99999" not in captured["text"] and "00000" not in captured["text"]


@pytest.mark.integration
def test_send_weekly_plan_rounds_kilometres(monkeypatch):
    """SV-07: the weekly plan said '63.195 km'."""
    bot = TitanTelegramBot(bot_token="", chat_id=None)
    captured = {}
    monkeypatch.setattr(bot, "send_message", lambda text: captured.setdefault("text", text) or True)

    bot.send_weekly_plan(
        {
            "total_km": 63.195,
            "daily_sessions": [
                {"day": "Monday", "session_type": "EASY", "distance_km": 10.000000000000002},
                {"day": "Tuesday", "session_type": "REST", "distance_km": 0},
            ],
        }
    )

    assert "• Volume: 63.2 km" in captured["text"]
    assert "*Monday* – EASY (10 km)" in captured["text"]
    assert "*Tuesday* – REST (0 km)" in captured["text"]
