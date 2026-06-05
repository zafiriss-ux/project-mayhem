"""Tests for GovernanceEngine — T5-52: CS confidence lock default fix."""
import pytest

from titan.science.governance_engine import GovernanceEngine


class TestCsConfidenceLockDefault:
    """T5-52: When cs_tracker has no confidence attr, lock must fire (default 0.0 not 1.0)."""

    @pytest.mark.unit
    def test_lock_fires_when_cs_tracker_has_no_confidence_attribute(self):
        """Object without confidence attr must trigger CS_CONFIDENCE_LOCK (ADR-0009)."""
        engine = GovernanceEngine()
        cs_tracker = object()  # no confidence attribute
        result = engine.check_cs_confidence_lock(cs_tracker)
        assert result["locked"] is True  # FAILS before fix (getattr default 1.0 >= threshold)

    @pytest.mark.unit
    def test_lock_fires_when_cs_tracker_is_none_object(self):
        """SimpleNamespace with no confidence field must trigger lock."""
        from types import SimpleNamespace
        engine = GovernanceEngine()
        cs_tracker = SimpleNamespace()  # no confidence attribute
        result = engine.check_cs_confidence_lock(cs_tracker)
        assert result["locked"] is True  # FAILS before fix

    @pytest.mark.unit
    def test_lock_does_not_fire_when_fully_calibrated(self):
        """A cs_tracker with confidence=1.0 must NOT trigger the lock."""
        from types import SimpleNamespace
        engine = GovernanceEngine()
        cs_tracker = SimpleNamespace(confidence=1.0)
        result = engine.check_cs_confidence_lock(cs_tracker)
        assert result["locked"] is False

    @pytest.mark.unit
    def test_lock_fires_when_confidence_below_threshold(self):
        """A cs_tracker with confidence below 0.70 must trigger the lock."""
        from types import SimpleNamespace
        engine = GovernanceEngine()
        cs_tracker = SimpleNamespace(confidence=0.5)
        result = engine.check_cs_confidence_lock(cs_tracker)
        assert result["locked"] is True

    @pytest.mark.unit
    def test_lock_result_contains_confidence_value_when_no_attr(self):
        """Lock result must expose confidence=0.0 when attribute missing (after fix)."""
        engine = GovernanceEngine()
        cs_tracker = object()
        result = engine.check_cs_confidence_lock(cs_tracker)
        assert result["confidence"] == 0.0  # FAILS before fix (returns 1.0)
