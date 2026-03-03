from pathlib import Path


def test_telegram_dependency_matches_telebot_import():
    """requirements.txt must install the package that provides `import telebot`."""
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "pyTelegramBotAPI==4.21.0" in requirements
    assert "python-telegram-bot" not in requirements
