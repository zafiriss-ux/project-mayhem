from titan.integrations.garmin_sync import GarminSync
from titan.integrations.telegram_bot import TitanTelegramBot
from titan.utils.constants import _Secret


def test_garmin_credentials_use_single_secret_container():
    sync = GarminSync(email="user@example.com", password="pw")

    assert isinstance(sync.email, _Secret)
    assert isinstance(sync.password, _Secret)
    assert not hasattr(sync, "_email_secret")
    assert not hasattr(sync, "_password_secret")


def test_telegram_token_uses_single_secret_container():
    bot = TitanTelegramBot(bot_token="token", chat_id="12345")

    assert isinstance(bot.bot_token, _Secret)
    assert not hasattr(bot, "_bot_token_secret")
