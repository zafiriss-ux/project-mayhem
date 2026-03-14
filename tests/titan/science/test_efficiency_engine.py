from titan.science.efficiency_engine import EfficiencyEngine


def _build_engine_with_history(previous_values: list[float], recent_values: list[float]) -> EfficiencyEngine:
    engine = EfficiencyEngine()
    for idx, ef in enumerate(previous_values + recent_values):
        engine.add_ef_measurement(f"2026-01-{idx + 1:02d}", ef)
    return engine


def test_analyze_ef_trend_returns_safe_outcome_when_previous_avg_is_zero() -> None:
    engine = _build_engine_with_history(previous_values=[0.0] * 7, recent_values=[0.02] * 7)

    trend = engine.analyze_ef_trend(weeks=1)

    assert trend == "Need historical data"


def test_analyze_ef_trend_returns_safe_outcome_when_previous_avg_is_negative() -> None:
    engine = _build_engine_with_history(previous_values=[-0.01] * 7, recent_values=[0.02] * 7)

    trend = engine.analyze_ef_trend(weeks=1)

    assert trend == "Need historical data"


def test_analyze_ef_trend_reports_improving_when_previous_avg_positive() -> None:
    engine = _build_engine_with_history(previous_values=[0.02] * 7, recent_values=[0.021] * 7)

    trend = engine.analyze_ef_trend(weeks=1)

    assert trend == "✓ IMPROVING: EF up 5.0% (aerobic gains)"
