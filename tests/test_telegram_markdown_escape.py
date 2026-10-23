"""OW-M1 (D-127): dynamic text in the briefing and the alerts cannot break legacy Markdown.

The bot sends with ``parse_mode="Markdown"``. An unescaped ``_``, ``*`` or backtick opens an
entity that must close, and ``[`` must start a link; otherwise Telegram refuses the whole
message ("can't parse entities"). A lock code such as ``HARD_STOP_SAFETY_GATES`` or an
athlete id such as ``athlete_2`` did exactly that. Synthetic data only.
"""

import pytest

from titan.integrations.telegram_bot import TitanTelegramBot, _escape_markdown_legacy

_CLOSERS = {"*": "*", "_": "_", "`": "`"}


def _legacy_markdown_ok(text: str) -> bool:
    """True when Telegram's legacy Markdown parser would accept *text*."""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in "_*`[":
            i += 2
            continue
        if ch in _CLOSERS:
            end = text.find(_CLOSERS[ch], i + 1)
            if end == -1:
                return False
            i = end + 1
            continue
        if ch == "[":
            close = text.find("](", i + 1)
            if close == -1 or text.find(")", close + 2) == -1:
                return False
            i = text.find(")", close + 2) + 1
            continue
        i += 1
    return True


@pytest.fixture
def bot():
    b = TitanTelegramBot(bot_token="", chat_id="12345")
    b.sent = []
    b.send_message = lambda text, **kw: b.sent.append(text) or True
    return b


def _coaching(**extra):
    return {
        "session_type": "EASY", "duration": "40 min", "optimal_time": "07:00", "dew_point": 10,
        "conditions": "GOOD", "hrv_status": "STABLE", "sleep_quality": 80, "readiness_score": 70,
        "nutrition_plan": "250g carbs, 120g protein", "shoe": "Daily trainer", **extra,
    }


def test_the_checker_rejects_what_telegram_rejects():
    assert not _legacy_markdown_ok("Why: HARD_STOP_SAFETY_GATES")
    assert not _legacy_markdown_ok("see [docs")
    assert _legacy_markdown_ok("*bold* and _it_ and `code` and [a](https://x.y)")
    assert _legacy_markdown_ok(r"HARD\_STOP\_SAFETY\_GATES")


@pytest.mark.parametrize("text", [
    "HARD_STOP_SAFETY_GATES", "a*b", "x`y", "[link", "_*`[", "plain", "", r"back\slash",
])
def test_escaped_text_always_parses(text):
    assert _legacy_markdown_ok(_escape_markdown_legacy(text))


def test_escaping_keeps_the_text_otherwise_unchanged():
    assert _escape_markdown_legacy("HARD_STOP *now* [x] `y`") == r"HARD\_STOP \*now\* \[x] \`y\`"
    assert _escape_markdown_legacy("Γεια σου, 12.5 km") == "Γεια σου, 12.5 km"


@pytest.mark.parametrize("field", [
    "session_type", "duration", "optimal_time", "conditions", "hrv_status", "nutrition_plan",
    "shoe", "primary_reason", "actionable_guidance", "hrv_stress_context", "special_note",
])
def test_a_briefing_with_markdown_characters_in_a_field_still_parses(bot, field):
    bot.send_daily_coaching(_coaching(**{field: "HARD_STOP_SAFETY_GATES *x* [y"}))
    assert len(bot.sent) == 1
    assert _legacy_markdown_ok(bot.sent[0])
    assert r"HARD\_STOP\_SAFETY\_GATES" in bot.sent[0]


def test_the_briefing_keeps_its_own_bold_headings(bot):
    bot.send_daily_coaching(_coaching(primary_reason="H2_HRV_DROP"))
    assert "🧭 *Why this decision:* H2\\_HRV\\_DROP" in bot.sent[0]
    assert "🏃 *Today:* EASY – 40 min" in bot.sent[0]


@pytest.mark.parametrize("title,message", [
    ("Morning briefing not delivered", "The morning briefing of athlete_2 for 2026-10-23 failed."),
    ("TITAN degraded mode", "TITAN degraded for >25h — persistence_degraded unresolved."),
    ("Data_Integrity", "lock *HARD_STOP_ACWR* [check"),
])
def test_an_alert_with_markdown_characters_still_parses(bot, title, message):
    bot.send_alert(title, message, level="critical")
    assert len(bot.sent) == 1
    assert _legacy_markdown_ok(bot.sent[0])
    assert bot.sent[0].startswith("🛑 *")


def test_a_structured_alert_with_a_lock_code_still_parses(bot):
    bot.send_structured_alert("safety_gate", "HARD_STOP_SAFETY_GATES", "lock HARD_STOP_SAFETY_GATES active")
    assert _legacy_markdown_ok(bot.sent[0])


def test_a_weekly_plan_with_a_long_run_still_parses(bot):
    # Before D-127 every plan with LONG_RUN (one underscore) was refused by Telegram.
    bot.send_weekly_plan({
        "week_start": "2026-10-26", "phase": "BUILD", "total_km": 40, "tsb_status": "FRESH",
        "daily_sessions": [
            {"day": "Saturday", "session_type": "LONG_RUN", "distance_km": 18, "details": "easy_pace *x*"},
        ],
        "motivation": "stay [sharp",
    })
    assert _legacy_markdown_ok(bot.sent[0])
    assert "*Saturday* – LONG\\_RUN (18 km)" in bot.sent[0]


def test_a_post_run_analysis_with_markdown_characters_still_parses(bot):
    bot.send_post_run_analysis({"distance_km": 10, "efficiency": "LOW_EF", "next_steps": "eat *now* [x"})
    assert _legacy_markdown_ok(bot.sent[0])
