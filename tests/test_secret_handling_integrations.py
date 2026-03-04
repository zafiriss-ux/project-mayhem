from titan.integrations.garmin_sync import GarminSync
from titan.integrations.telegram_bot import TitanTelegramBot


def test_garmin_credentials_use_single_secret_container_and_are_redacted():
    sync = GarminSync(email="user@example.com", password="pw")

    assert sync.email.reveal() == "user@example.com"
    assert sync.password.reveal() == "pw"
    assert str(sync.email) == "***"
    assert repr(sync.password) == "'***'"
    assert not hasattr(sync, "_email_secret")
    assert not hasattr(sync, "_password_secret")


def test_telegram_token_uses_single_secret_container_and_is_redacted():
    bot = TitanTelegramBot(bot_token="token", chat_id="12345")

    assert bot.bot_token.reveal() == "token"
    assert str(bot.bot_token) == "***"
    assert repr(bot.bot_token) == "'***'"
    assert not hasattr(bot, "_bot_token_secret")
