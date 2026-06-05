"""Tests for RCP engine edge conditions."""

import pytest

from titan.science.rcp_engine import RCPEngine


@pytest.mark.unit
def test_estimate_rcp_from_progressive_test_detects_inflection_happy_path() -> None:
    """RCP is detected when HR:pace efficiency inflects sharply."""
    pace_segments = [360.0, 330.0, 300.0, 285.0, 270.0]
    hr_segments = [130, 142, 154, 170, 176]
    rpe_segments = [3.0, 4.0, 5.0, 7.0, 8.0]

    rcp_hr, rcp_pace, rcp_rpe, explanation = RCPEngine.estimate_rcp_from_progressive_test(
        pace_segments,
        hr_segments,
        rpe_segments,
    )

    assert rcp_hr == 154
    assert rcp_pace == 300.0
    assert rcp_rpe == 5.0
    assert explanation == "RCP detected at segment 3: Sharp efficiency drop"


@pytest.mark.unit
def test_estimate_rcp_from_progressive_test_rejects_zero_or_negative_pace() -> None:
    """Non-positive pace values should return the safe non-computable outcome."""
    pace_segments = [360.0, 0.0, -15.0, 285.0]
    hr_segments = [130, 142, 154, 170]
    rpe_segments = [3.0, 4.0, 5.0, 7.0]

    result = RCPEngine.estimate_rcp_from_progressive_test(
        pace_segments,
        hr_segments,
        rpe_segments,
    )

    assert result == (None, None, None, "Invalid pace segments for RCP detection")


@pytest.mark.unit
def test_estimate_rcp_from_progressive_test_rejects_exact_zero_pace() -> None:
    """A zero pace segment must trigger the safe invalid-path return."""
    pace_segments = [360.0, 330.0, 0.0, 285.0]
    hr_segments = [130, 142, 154, 170]
    rpe_segments = [3.0, 4.0, 5.0, 7.0]

    result = RCPEngine.estimate_rcp_from_progressive_test(
        pace_segments,
        hr_segments,
        rpe_segments,
    )

    assert result == (None, None, None, "Invalid pace segments for RCP detection")
