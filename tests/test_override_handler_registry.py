from titan.config.thresholds import CANONICAL_LOCK_CODES
from titan.science.governance_engine import OVERRIDE_HANDLERS


def test_override_handlers_cover_all_canonical_lock_codes():
    assert set(OVERRIDE_HANDLERS) == set(CANONICAL_LOCK_CODES)


def test_override_handlers_are_callable_for_every_lock_code():
    assert all(callable(handler) for handler in OVERRIDE_HANDLERS.values())
