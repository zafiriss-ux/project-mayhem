"""Root conftest.py — shared fixtures for all test files."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from freezegun import freeze_time as _freeze_time


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Point the home folder at a throwaway directory for the whole run.

    ``DatabaseManager()`` without ``db_dir`` and ``python -m titan`` open the
    real data folder (``~/Documents/TITAN``, on Windows under ``USERPROFILE``),
    the same database the installed TITAN.exe uses. A test run from a branch
    with a newer schema would migrate that database, and the installed exe
    would then refuse to open it (INV-25). Set before collection, so imports
    and subprocesses (which copy ``os.environ``) see it too.
    """
    home = Path(tempfile.mkdtemp(prefix="titan-test-home-"))
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ["LOCALAPPDATA"] = str(home / "AppData" / "Local")


@pytest.fixture(autouse=True)
def _reset_titan_settings_cache():
    """Reset the cached TitanSettings singleton around every test (P15-ARCH5).

    ``titan.config.settings.get_settings()`` is ``@functools.lru_cache``-d, so a
    ``TitanSettings`` instance constructed in one test (reading the then-current
    environment) would otherwise persist process-wide and shadow a later test's
    ``monkeypatch.setenv(...)`` — the settings object never re-reads ``os.environ``.
    That cross-test leak makes env-sensitive gates (ML kill-switch, JWT/auth,
    Garmin token encryption, dev-env detection) pass or fail based on collection
    order rather than their own environment. Clearing the cache before and after
    each test makes every test observe exactly its own environment. This codifies
    globally the idiom already used ad hoc in tests/test_garmin_sync.py.
    """
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def frozen_date():
    """Freeze datetime.now() to today's real date, eliminating midnight/DST race conditions.

    Freezes to the actual calendar date at fixture setup time so that SQLite
    date('now') queries (which freezegun does not patch) stay aligned with
    Python datetime.now() calls inside the test.

    Usage: add ``@pytest.mark.usefixtures("frozen_date")`` to a test class or method
    that computes 'today' via datetime.now().
    """
    today = datetime.now().strftime("%Y-%m-%d")
    with _freeze_time(today):
        yield today
