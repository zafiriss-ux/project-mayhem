import pytest

from titan.science.readiness_engine import ReadinessEngine

# ── T5-53: null HRV guard ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_analyze_readiness_does_not_raise_when_today_hrv_is_none() -> None:
    """T5-53: TypeError guard — today_hrv=None must not raise."""
    result = ReadinessEngine.analyze_readiness(
        today_hrv=None,  # type: ignore[arg-type]
        baseline_hrv=50.0,
        today_rhr=50.0,
        baseline_rhr=50.0,
        sleep_score=75,
        soreness=2,
    )
    assert isinstance(result["score"], int)
    assert result["hrv_delta_pts"] is None


@pytest.mark.unit
def test_analyze_readiness_does_not_raise_when_baseline_hrv_is_none() -> None:
    """T5-53: TypeError guard — baseline_hrv=None must not raise."""
    result = ReadinessEngine.analyze_readiness(
        today_hrv=50.0,
        baseline_hrv=None,  # type: ignore[arg-type]
        today_rhr=50.0,
        baseline_rhr=50.0,
        sleep_score=75,
        soreness=2,
    )
    assert isinstance(result["score"], int)
    assert result["hrv_delta_pts"] is None


@pytest.mark.unit
def test_analyze_readiness_skips_hrv_component_when_both_hrv_are_none() -> None:
    """T5-53: when both HRV values are None, score is computed from other components only."""
    result = ReadinessEngine.analyze_readiness(
        today_hrv=None,  # type: ignore[arg-type]
        baseline_hrv=None,  # type: ignore[arg-type]
        today_rhr=50.0,
        baseline_rhr=50.0,
        sleep_score=85,  # +5 bonus
        soreness=0,
    )
    # 100 + 5 (sleep bonus) = 105, clamped to 100
    assert result["score"] == 100
    assert result["hrv_delta_pts"] is None


# ── existing threshold tests ──────────────────────────────────────────────────

@pytest.mark.unit
def test_analyze_readiness_covers_hrv_minus10_sleep_fair_and_soreness_moderate() -> None:
    # hrv_diff=-6 (between -8 and -5), sleep=65 (60-69), soreness=6 (>5)
    result = ReadinessEngine.analyze_readiness(
        today_hrv=44.0,
        baseline_hrv=50.0,
        today_rhr=50.0,
        baseline_rhr=50.0,
        sleep_score=65,
        soreness=6,
    )

    # 100 -10 (hrv) -8 (sleep) -10 (soreness) = 72
    assert result["score"] == 72
    assert result["status"] == "👍 GOOD"


@pytest.mark.unit
def test_analyze_readiness_soreness_exactly_five_has_no_soreness_deduction() -> None:
    # Boundary check: soreness == 5 should not trigger >5 deduction branch
    result = ReadinessEngine.analyze_readiness(
        today_hrv=50.0,
        baseline_hrv=50.0,
        today_rhr=50.0,
        baseline_rhr=50.0,
        sleep_score=85,
        soreness=5,
    )

    # baseline 100 +5 sleep bonus = 105 clamped to 100
    assert result["score"] == 100
    assert result["status"] == "✅ EXCELLENT"
