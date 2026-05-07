"""Root conftest.py — shared fixtures for all test files."""
from __future__ import annotations

from datetime import datetime

import pytest
from freezegun import freeze_time as _freeze_time


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
