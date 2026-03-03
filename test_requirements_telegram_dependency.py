from pathlib import Path


RUNTIME_DEPENDENCIES = {
    "numpy==1.26.4",
    "garminconnect==0.2.13",
    "requests==2.32.4",
    "pyTelegramBotAPI==4.21.0",
}

DEV_DEPENDENCIES = {
    "pytest==8.1.1",
    "pytest-cov==4.1.0",
    "hypothesis==6.100.0",
    "ruff==0.3.7",
    "mypy==1.9.0",
}

BUILD_DEPENDENCIES = {
    "pyinstaller==6.4.0",
    "pywin32==306; sys_platform == 'win32'",
}


def test_telegram_dependency_matches_telebot_import():
    """requirements.txt must install the package that provides `import telebot`."""
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "pyTelegramBotAPI==4.21.0" in requirements
    assert "python-telegram-bot" not in requirements


def test_runtime_requirements_are_runtime_only():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    for dep in RUNTIME_DEPENDENCIES:
        assert dep in requirements

    for dep in DEV_DEPENDENCIES | BUILD_DEPENDENCIES:
        assert dep not in requirements

    for removed in {"scikit-learn==1.4.2", "pandas==2.2.1", "pyyaml==6.0.1"}:
        assert removed not in requirements


def test_dev_and_build_requirements_are_split_correctly():
    dev_requirements = Path("requirements-dev.txt").read_text(encoding="utf-8")
    build_requirements = Path("requirements-build.txt").read_text(encoding="utf-8")

    for dep in DEV_DEPENDENCIES:
        assert dep in dev_requirements
        assert dep not in build_requirements

    for dep in BUILD_DEPENDENCIES:
        assert dep in build_requirements
        assert dep not in dev_requirements
