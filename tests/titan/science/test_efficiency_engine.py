import pytest

from titan.science.efficiency_engine import EfficiencyEngine

# ── T5-47: pace=0 / pace=None guard ──────────────────────────────────────────

@pytest.mark.unit
def test_calculate_efficiency_factor_returns_none_when_pace_is_zero() -> None:
    """T5-47: ZeroDivisionError guard — pace=0 must return None, not raise."""
    result = EfficiencyEngine.calculate_efficiency_factor(
        avg_pace_sec_per_km=0, avg_hr=150
    )
    assert result is None


@pytest.mark.unit
def test_calculate_efficiency_factor_returns_none_when_pace_is_none() -> None:
    """T5-47: TypeError guard — pace=None must return None, not raise."""
    result = EfficiencyEngine.calculate_efficiency_factor(
        avg_pace_sec_per_km=None, avg_hr=150  # type: ignore[arg-type]
    )
    assert result is None


@pytest.mark.unit
def test_calculate_efficiency_factor_happy_path_returns_ef() -> None:
    """Regression: valid 5:00/km @ 150 bpm = 1000/300/150 ≈ 0.02222."""
    result = EfficiencyEngine.calculate_efficiency_factor(
        avg_pace_sec_per_km=300.0, avg_hr=150.0
    )
    assert result == pytest.approx(0.02222, rel=1e-3)


# ── trend helpers ─────────────────────────────────────────────────────────────

def _build_engine_with_history(previous_values: list[float], recent_values: list[float]) -> EfficiencyEngine:
    engine = EfficiencyEngine()
    for idx, ef in enumerate(previous_values + recent_values):
        engine.add_ef_measurement(f"2026-01-{idx + 1:02d}", ef)
    return engine


@pytest.mark.unit
def test_analyze_ef_trend_returns_safe_outcome_when_previous_avg_is_zero() -> None:
    engine = _build_engine_with_history(previous_values=[0.0] * 7, recent_values=[0.02] * 7)

    trend = engine.analyze_ef_trend(weeks=1)

    assert trend == "Need historical data"


@pytest.mark.unit
def test_analyze_ef_trend_returns_safe_outcome_when_previous_avg_is_negative() -> None:
    engine = _build_engine_with_history(previous_values=[-0.01] * 7, recent_values=[0.02] * 7)

    trend = engine.analyze_ef_trend(weeks=1)

    assert trend == "Need historical data"


@pytest.mark.unit
def test_analyze_ef_trend_reports_improving_when_previous_avg_positive() -> None:
    engine = _build_engine_with_history(previous_values=[0.02] * 7, recent_values=[0.021] * 7)

    trend = engine.analyze_ef_trend(weeks=1)

    assert trend == "✓ IMPROVING: EF up 5.0% (aerobic gains)"
