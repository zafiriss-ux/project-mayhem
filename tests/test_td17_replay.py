"""
TD-17: Telegram override replay protection tests.

Verifies the nonce-based one-time-use mechanism that prevents duplicate
override confirmations from network retries or multi-tap.
"""

import time

from titan.integrations.telegram_bot import (
    _PENDING_OVERRIDES,
    _consume_override_nonce,
    _create_override_nonce,
)


def test_nonce_valid_first_use():
    nonce = _create_override_nonce("dec-1")
    result = _consume_override_nonce(nonce)
    assert result == "dec-1"


def test_nonce_invalid_second_use():
    nonce = _create_override_nonce("dec-1")
    _consume_override_nonce(nonce)  # first use
    result = _consume_override_nonce(nonce)
    assert result is None  # replay blocked


def test_nonce_expired():
    nonce = _create_override_nonce("dec-1")
    # Manually expire it
    _PENDING_OVERRIDES[nonce] = ("dec-1", time.monotonic() - 1)
    result = _consume_override_nonce(nonce)
    assert result is None


def test_nonce_invalid_unknown():
    result = _consume_override_nonce("not-a-real-nonce")
    assert result is None


def test_different_decisions_different_nonces():
    n1 = _create_override_nonce("dec-1")
    n2 = _create_override_nonce("dec-2")
    assert n1 != n2
    assert _consume_override_nonce(n1) == "dec-1"
    assert _consume_override_nonce(n2) == "dec-2"
