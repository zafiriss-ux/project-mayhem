from pathlib import Path


def _dependency_lines(path: str) -> list[str]:
    dependencies: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        dependency = stripped.split("#", maxsplit=1)[0].strip()
        if dependency:
            dependencies.append(dependency)
    return dependencies


def test_requirements_use_pytelegrambotapi_for_telebot():
    requirements = _dependency_lines("requirements.txt")
    telegram_module = Path("titan/integrations/telegram_bot.py").read_text(encoding="utf-8")

    assert "pyTelegramBotAPI==4.33.0" in requirements
    assert "import telebot" in telegram_module


def test_requirements_do_not_include_python_telegram_bot_package():
    requirements = _dependency_lines("requirements.txt")

    assert all("python-telegram-bot" not in dependency for dependency in requirements)
