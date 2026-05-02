from pathlib import Path

RUNTIME_DEPENDENCIES = {
    "numpy==1.26.4",
    "garminconnect==0.3.2",
    "requests==2.33.0",
    "pyTelegramBotAPI==4.21.0",
    "sqlalchemy==2.0.39",
    "alembic==1.15.2",
    "psycopg2-binary==2.9.10",
    "fastapi==0.115.0",
    "pyjwt[crypto]==2.12.0",
    "bcrypt==4.2.0",
    "cryptography==41.0.7",
    "import-linter==2.11",
    "schemathesis==4.15.2",
    "mutmut==3.5.0",
}

DEV_DEPENDENCIES = {
    "pytest==8.1.1",
    "pytest-cov==4.1.0",
    "pytest-timeout==2.3.1",
    "hypothesis==6.100.0",
    "ruff==0.15.8",
    "mypy==1.19.1",
    "httpx==0.27.2",
    "pre-commit==3.7.1",
    "freezegun==1.5.1",
}

BUILD_DEPENDENCIES = {
    "pyinstaller==6.4.0",
    "pywin32==306; sys_platform == 'win32'",
}

REMOVED_LEGACY_DEPENDENCIES = {
    "scikit-learn==1.4.2",
    "pandas==2.2.1",
    "pyyaml==6.0.1",
}


def _read_dependency_lines(path: str) -> set[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    dependencies: set[str] = set()

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        dependency = stripped.split("#", maxsplit=1)[0].strip()
        if dependency:
            dependencies.add(dependency)

    return dependencies


def test_telegram_dependency_matches_telebot_import():
    """requirements.txt must install the package that provides `import telebot`."""
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    telegram_module = Path("titan/integrations/telegram_bot.py").read_text(encoding="utf-8")

    assert "pyTelegramBotAPI==4.21.0" in requirements
    assert "python-telegram-bot" not in requirements
    assert "import telebot" in telegram_module


def test_runtime_requirements_are_runtime_only():
    runtime_dependencies = _read_dependency_lines("requirements.txt")

    assert runtime_dependencies == RUNTIME_DEPENDENCIES

    for removed in REMOVED_LEGACY_DEPENDENCIES:
        assert removed not in runtime_dependencies


def test_dev_and_build_requirements_are_split_correctly():
    dev_requirements = _read_dependency_lines("requirements-dev.txt")
    build_requirements = _read_dependency_lines("requirements-build.txt")

    assert dev_requirements == DEV_DEPENDENCIES
    assert build_requirements == BUILD_DEPENDENCIES

    assert dev_requirements.isdisjoint(build_requirements)
