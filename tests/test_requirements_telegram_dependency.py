import re
from pathlib import Path

# Package names only: exact versions live in the requirements files and are
# bumped by Dependabot. This test guards the runtime/dev/build split, so it
# compares names; pinning (==) is asserted separately below.
RUNTIME_DEPENDENCIES = {
    "garminconnect",
    "requests",
    "pytelegrambotapi",
    "sqlalchemy",
    "alembic",
    # psycopg2-binary removed from active requirements (TD-DEP-01) — see requirements.txt
    "fastapi",
    "uvicorn",
    "pyjwt",
    "bcrypt",
    "cryptography",
    "import-linter",
    "schemathesis",
    "mutmut",
    "pip-audit",
    "prometheus-client",  # TD-OBS: Prometheus scrape endpoint
    "pydantic-settings",  # P15-ARCH5: centralised env-var config
}

DEV_DEPENDENCIES = {
    "pytest",
    "pytest-cov",
    "pytest-timeout",
    "hypothesis",
    "ruff",
    "mypy",
    "httpx",
    "pre-commit",
    "freezegun",
}

BUILD_DEPENDENCIES = {
    "pyinstaller",
    "pywin32",
}

REMOVED_LEGACY_DEPENDENCIES = {
    "scikit-learn",
    "pandas",
    "pyyaml",
}

_NAME_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def _package_name(requirement: str) -> str:
    match = _NAME_PATTERN.match(requirement)
    assert match, f"Unparseable requirement line: {requirement!r}"
    return match.group(1).lower().replace("_", "-")


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

    assert "pyTelegramBotAPI==" in requirements
    assert "python-telegram-bot" not in requirements
    assert "import telebot" in telegram_module


def _read_dependency_names(path: str) -> set[str]:
    return {_package_name(dependency) for dependency in _read_dependency_lines(path)}


def test_runtime_requirements_are_runtime_only():
    runtime_dependencies = _read_dependency_names("requirements.txt")

    assert runtime_dependencies == RUNTIME_DEPENDENCIES

    for removed in REMOVED_LEGACY_DEPENDENCIES:
        assert removed not in runtime_dependencies


def test_dev_and_build_requirements_are_split_correctly():
    dev_requirements = _read_dependency_names("requirements-dev.txt")
    build_requirements = _read_dependency_names("requirements-build.txt")

    assert dev_requirements == DEV_DEPENDENCIES
    assert build_requirements == BUILD_DEPENDENCIES

    assert dev_requirements.isdisjoint(build_requirements)


def test_all_requirements_are_pinned_exactly():
    for path in ("requirements.txt", "requirements-dev.txt", "requirements-build.txt"):
        for dependency in _read_dependency_lines(path):
            assert "==" in dependency, f"{path}: {dependency!r} is not pinned with =="
