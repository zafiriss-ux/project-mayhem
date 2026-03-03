"""Hygiene checks for canonical ACWR threshold ownership."""

from titan.config import thresholds
from titan.utils import constants


def test_legacy_acwr_safe_constants_removed_from_constants_module():
    """ACWR safe band must live only in titan.config.thresholds."""
    assert not hasattr(constants, 'ACWR_SAFE_MIN')
    assert not hasattr(constants, 'ACWR_SAFE_MAX')


def test_vo2_acwr_thresholds_remain_canonical_source():
    """Canonical VO2 ACWR thresholds are still defined in thresholds.py."""
    assert thresholds.VO2_ACWR_MIN == 0.80
    assert thresholds.VO2_ACWR_MAX == 1.30
