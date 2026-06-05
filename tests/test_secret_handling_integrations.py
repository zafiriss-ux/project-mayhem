import pytest

from titan.integrations.garmin_sync import GarminSync
from titan.integrations.telegram_bot import TitanTelegramBot


@pytest.mark.unit
def test_garmin_credentials_use_single_secret_container_and_are_redacted():
    sync = GarminSync(email="user@example.com", password="pw")

    assert sync.email.get_secret_value() == "user@example.com"
    assert sync.password.get_secret_value() == "pw"
    assert "user@example.com" not in str(sync.email)
    assert "pw" not in repr(sync.password)
    assert not hasattr(sync, "_email_secret")
    assert not hasattr(sync, "_password_secret")


@pytest.mark.unit
def test_telegram_token_uses_single_secret_container_and_is_redacted():
    bot = TitanTelegramBot(bot_token="token", chat_id="12345")

    assert bot.bot_token.get_secret_value() == "token"
    assert "token" not in str(bot.bot_token)
    assert "token" not in repr(bot.bot_token)
    assert not hasattr(bot, "_bot_token_secret")
