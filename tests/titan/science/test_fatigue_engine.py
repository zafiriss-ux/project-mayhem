from titan.science.fatigue_engine import FatigueEngine


def test_classify_fatigue_uses_configured_soreness_threshold(monkeypatch) -> None:
    monkeypatch.setattr(
        'titan.science.fatigue_engine.FATIGUE_SORENESS_PERIPHERAL_MIN',
        7,
    )

    severity, fatigue_types = FatigueEngine.classify_fatigue(
        hr_suppression=False,
        rpe_mismatch=False,
        pace_hr_divergence=False,
        soreness=7,
    )

    assert severity == 'MEDIUM'
    assert fatigue_types == ['PERIPHERAL']


def test_classify_fatigue_below_configured_soreness_threshold_returns_low(monkeypatch) -> None:
    monkeypatch.setattr(
        'titan.science.fatigue_engine.FATIGUE_SORENESS_PERIPHERAL_MIN',
        7,
    )

    severity, fatigue_types = FatigueEngine.classify_fatigue(
        hr_suppression=False,
        rpe_mismatch=False,
        pace_hr_divergence=False,
        soreness=6,
    )

    assert severity == 'LOW'
    assert fatigue_types == ['NONE']
