"""D17: Telegram per-command rate limit — unit tests."""

from __future__ import annotations

import time

import pytest

from titan.integrations.telegram_bot import _CMD_COOLDOWN_S, _check_rate_limit, _cmd_rate


@pytest.fixture(autouse=True)
def _clear_rate_state():
    """Reset global rate-limit state before each test."""
    _cmd_rate.clear()
    yield
    _cmd_rate.clear()


@pytest.mark.unit
def test_rate_limit_blocks_repeat_command():
    """Second call within the cooldown window returns False."""
    assert _check_rate_limit(123, "sync") is True
    assert _check_rate_limit(123, "sync") is False


@pytest.mark.unit
def test_rate_limit_allows_different_commands():
    """Different commands for the same chat_id are not mutually blocked."""
    assert _check_rate_limit(123, "sync") is True
    assert _check_rate_limit(123, "today") is True
