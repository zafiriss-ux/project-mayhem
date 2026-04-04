"""HD-05 / OBS-038: AuthenticatedRateLimiter LRU key-ceiling tests."""

from __future__ import annotations

import json
import logging
from time import monotonic

import pytest

from titan.api.main import AuthenticatedRateLimiter, RateLimitConfig
from titan.config.thresholds import RATE_LIMITER_MAX_KEYS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_limiter() -> AuthenticatedRateLimiter:
    return AuthenticatedRateLimiter(config=RateLimitConfig(coach_per_minute=100, athlete_per_minute=30))


def _inject_key(limiter: AuthenticatedRateLimiter, key: tuple, ts: float) -> None:
    """Directly insert a key into the limiter's internal dict (bypasses auth)."""
    limiter._requests[key].append(ts)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRateLimiterLRUCeiling:
    def test_key_count_bounded_after_exceeding_ceiling(self) -> None:
        """Inserting 10_001 keys must leave len(requests) <= RATE_LIMITER_MAX_KEYS."""
        limiter = _make_limiter()
        now = monotonic()

        # Pre-fill the dict up to ceiling
        for i in range(RATE_LIMITER_MAX_KEYS):
            key = (f"user-{i}", "ATHLETE", f"GET:/path/{i}")
            _inject_key(limiter, key, now + i)

        assert len(limiter._requests) == RATE_LIMITER_MAX_KEYS

        # Inject one more key beyond the ceiling to trigger eviction
        extra_key = ("user-overflow", "ATHLETE", "GET:/overflow")
        _inject_key(limiter, extra_key, now + RATE_LIMITER_MAX_KEYS + 1)

        # Call eviction manually (mirrors what __call__ does while holding the lock)
        limiter._evict_lru_keys()

        assert len(limiter._requests) <= RATE_LIMITER_MAX_KEYS

    def test_eviction_removes_least_recently_used_keys(self) -> None:
        """Eviction must remove the key with the oldest last-access timestamp."""
        limiter = _make_limiter()
        now = monotonic()

        oldest_key = ("old-user", "ATHLETE", "GET:/old")
        newer_key = ("new-user", "ATHLETE", "GET:/new")

        limiter._requests[oldest_key].append(now - 100.0)  # old access
        limiter._requests[newer_key].append(now)           # recent access

        # Fill remaining slots to just above ceiling with recent keys
        for i in range(RATE_LIMITER_MAX_KEYS - 1):
            key = (f"u-{i}", "ATHLETE", f"GET:/p/{i}")
            _inject_key(limiter, key, now)

        assert len(limiter._requests) == RATE_LIMITER_MAX_KEYS + 1

        limiter._evict_lru_keys()

        assert len(limiter._requests) == RATE_LIMITER_MAX_KEYS
        assert oldest_key not in limiter._requests
        assert newer_key in limiter._requests

    def test_eviction_event_emitted_as_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """_evict_lru_keys must emit a limiter_eviction WARNING log event."""
        limiter = _make_limiter()
        now = monotonic()

        for i in range(RATE_LIMITER_MAX_KEYS + 2):
            key = (f"u-{i}", "ATHLETE", f"GET:/p/{i}")
            _inject_key(limiter, key, now + i)

        with caplog.at_level(logging.WARNING, logger="titan.api.main"):
            limiter._evict_lru_keys()

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, "Expected at least one WARNING log entry"

        # Parse the JSON payload and verify action + keys_evicted field
        payload = json.loads(warning_records[0].getMessage())
        assert payload["action"] == "limiter_eviction"
        assert payload["keys_evicted"] >= 2

    def test_existing_rate_limit_behavior_unchanged(self) -> None:
        """Existing keys and their counters must not be affected during normal operation."""
        limiter = _make_limiter()
        now = monotonic()
        key = ("coach-1", "COACH", "GET:/athletes/a1/dashboard")

        # Insert 3 requests for this key
        for offset in (0.0, 1.0, 2.0):
            _inject_key(limiter, key, now + offset)

        assert len(limiter._requests[key]) == 3

        # Eviction must not touch this key when we're well under ceiling
        limiter._evict_lru_keys()  # n_to_evict == 0, no-op

        assert len(limiter._requests[key]) == 3

    def test_evict_lru_is_noop_when_under_ceiling(self) -> None:
        """No eviction and no log emission when key count is at or below ceiling."""
        limiter = _make_limiter()
        now = monotonic()

        for i in range(5):
            _inject_key(limiter, (f"u-{i}", "ATHLETE", f"GET:/p/{i}"), now + i)

        # Must be a no-op
        limiter._evict_lru_keys()
        assert len(limiter._requests) == 5

    def test_multiple_excess_keys_all_evicted(self) -> None:
        """If 50 keys are over ceiling, all 50 must be evicted in one call."""
        limiter = _make_limiter()
        now = monotonic()
        excess = 50

        for i in range(RATE_LIMITER_MAX_KEYS + excess):
            _inject_key(limiter, (f"u-{i}", "ATHLETE", f"GET:/p/{i}"), now + i)

        limiter._evict_lru_keys()
        assert len(limiter._requests) == RATE_LIMITER_MAX_KEYS
