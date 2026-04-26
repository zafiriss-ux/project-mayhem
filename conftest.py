"""Root conftest.py — shared fixtures for all test files."""
from __future__ import annotations

import pytest
from freezegun import freeze_time as _freeze_time


@pytest.fixture
def frozen_date():
    """Freeze datetime.now() to a fixed date, eliminating midnight/DST race conditions.

    Usage: add ``@pytest.mark.usefixtures("frozen_date")`` to a test class or method
    that computes 'today' via datetime.now().
    """
    with _freeze_time("2026-04-26"):
        yield "2026-04-26"
