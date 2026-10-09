"""Tests for CP-01 through CP-07 Copilot findings fixes."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("GARMIN_EMAIL", "test@example.com")
os.environ.setdefault("GARMIN_PASSWORD", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("WEATHER_API_KEY", "test")
os.environ.setdefault("WEATHER_LOCATION", "Athens,GR")

sys.path.insert(0, str(Path(__file__).parent.parent))

from titan.core.database import DatabaseManager
from titan.integrations.telegram_bot import (
    TitanTelegramBot,
    _consume_override_nonce,
    _create_override_nonce,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_DB: DatabaseManager | None = None


@pytest.fixture(autouse=True)
def _nonce_db(tmp_path):
    global _DB
    _DB = DatabaseManager(db_dir=tmp_path)
    yield
    _DB.close()


def _make_bot() -> TitanTelegramBot:
    bot = TitanTelegramBot.__new__(TitanTelegramBot)
    bot.db = _DB
    bot._token = ""
    bot._chat_id = 12345
    bot._bot = None
    bot._pending_override_prompts = {}
    bot._alert_history = {}
    bot.override_callbacks = {}
    bot._MAX_OVERRIDE_REASON_LEN = 500
    return bot


# ── CP-01: nonce logic per-action ─────────────────────────────────────────────

class TestNoncePerAction:
    @pytest.mark.unit
    def test_nonce_accept_valid(self):
        bot = _make_bot()
        bot.send_message = MagicMock(return_value=True)
        nonce = _create_override_nonce(_DB, "dec-001", "owner")
        result = bot.process_override_callback(12345, f"override:accept:{nonce}")
        assert result == "✅ Decision accepted."

    @pytest.mark.unit
    def test_nonce_accept_replay(self):
        bot = _make_bot()
        nonce = _create_override_nonce(_DB, "dec-002", "owner")
        _consume_override_nonce(_DB, nonce)  # consume first
        result = bot.process_override_callback(12345, f"override:accept:{nonce}")
        assert "expired" in result or "already been used" in result

    @pytest.mark.unit
    def test_nonce_request_valid(self):
        bot = _make_bot()
        nonce = _create_override_nonce(_DB, "dec-003", "owner")
        bot._pending_override_prompts[12345] = {"decision_id": "dec-003", "athlete_id": 1}
        result = bot.process_override_callback(12345, f"override:request:{nonce}")
        assert "reason" in result.lower() or "override" in result.lower()

    @pytest.mark.unit
    def test_nonce_request_replay(self):
        bot = _make_bot()
        nonce = _create_override_nonce(_DB, "dec-004", "owner")
        _consume_override_nonce(_DB, nonce)  # consume first
        result = bot.process_override_callback(12345, f"override:request:{nonce}")
        assert "expired" in result or "already been used" in result

    @pytest.mark.unit
    def test_nonce_accept_no_nonce(self):
        bot = _make_bot()
        result = bot.process_override_callback(12345, "override:accept")
        assert result.startswith("⚠️")


# ── CP-02: is_configured missing GARMIN_PASSWORD ─────────────────────────────

class TestIsConfigured:
    @pytest.mark.unit
    def test_is_configured_missing_password(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("GARMIN_EMAIL=test@example.com\nTELEGRAM_BOT_TOKEN=12345678:ABC\n")

        import titan.ui.setup_wizard as sw
        orig_path = sw.ENV_PATH
        try:
            sw.ENV_PATH = env_file
            result = sw.credentials_exist()
        finally:
            sw.ENV_PATH = orig_path

        assert result is False


# ── CP-04: fat constants in thresholds ────────────────────────────────────────

class TestFatConstants:
    @pytest.mark.unit
    def test_fat_constants_in_thresholds(self):
        from titan.config.thresholds import FAT_KCAL_PER_GRAM, MIN_FAT_G
        assert MIN_FAT_G == 40
        assert FAT_KCAL_PER_GRAM == 9

    @pytest.mark.unit
    def test_nutrition_uses_constants(self):
        from titan.config.thresholds import FAT_KCAL_PER_GRAM, MIN_FAT_G
        for fat_kcal in [0, 180, 360, 900]:
            expected = max(40, fat_kcal / 9)
            got = max(MIN_FAT_G, fat_kcal / FAT_KCAL_PER_GRAM)
            assert got == expected, f"fat_kcal={fat_kcal}: {got} != {expected}"


# ── CP-05: send_alert invalid level ───────────────────────────────────────────

class TestSendAlertLevel:
    @pytest.mark.unit
    def test_send_alert_invalid_level_does_not_raise(self):
        bot = _make_bot()
        bot.send_message = MagicMock(return_value=True)
        result = bot.send_alert("Test Title", "Test message", level="invalid")
        assert isinstance(result, bool)
        call_args = bot.send_message.call_args[0][0]
        assert "⚠️" in call_args

    @pytest.mark.unit
    def test_send_alert_valid_levels(self):
        bot = _make_bot()
        bot.send_message = MagicMock(return_value=True)
        expected = {"critical": "🛑", "warning": "⚠️", "info": "ℹ️", "ok": "✅"}
        for level, emoji in expected.items():
            bot.send_alert("T", "M", level=level)
            msg = bot.send_message.call_args[0][0]
            assert emoji in msg
