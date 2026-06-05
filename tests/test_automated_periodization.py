import pytest

from titan.science.automated_periodization import (
    AutomatedPeriodizationEngine,
    PeriodizationSuggestion,
)


@pytest.mark.unit
def test_high_readiness_low_fatigue_suggests_build():
    engine = AutomatedPeriodizationEngine()
    suggestion = engine.suggest(
        {
            'readiness': 0.82,
            'fatigue': 0.33,
            'monotony': 1.2,
            'compliance': 0.91,
        }
    )

    assert isinstance(suggestion, PeriodizationSuggestion)
    assert suggestion.recommended_focus == 'BUILD'
    assert suggestion.volume_adjustment_pct > 0
    assert suggestion.mode == 'SUGGEST_ONLY'


@pytest.mark.unit
def test_low_readiness_or_high_fatigue_suggests_recovery():
    engine = AutomatedPeriodizationEngine()
    suggestion = engine.suggest(
        {
            'readiness': 0.30,
            'fatigue': 0.80,
            'monotony': 1.4,
            'compliance': 0.88,
        }
    )

    assert suggestion.recommended_focus == 'RECOVERY'
    assert suggestion.volume_adjustment_pct < 0
    assert suggestion.intensity_adjustment_pct < 0


@pytest.mark.unit
def test_high_monotony_blocks_build_and_caps_load():
    engine = AutomatedPeriodizationEngine()
    suggestion = engine.suggest(
        {
            'readiness': 0.80,
            'fatigue': 0.35,
            'monotony': 1.95,
            'compliance': 0.95,
        }
    )

    assert suggestion.recommended_focus != 'BUILD'
    assert suggestion.volume_adjustment_pct <= -0.08
    assert suggestion.intensity_adjustment_pct <= -0.05


@pytest.mark.unit
def test_dict_contract_is_stable():
    engine = AutomatedPeriodizationEngine()
    payload = engine.as_dict(engine.suggest({}))

    assert set(payload) == {
        'recommended_focus',
        'volume_adjustment_pct',
        'intensity_adjustment_pct',
        'confidence',
        'mode',
        'model_name',
        'evidence_label',
    }
    assert payload['mode'] == 'SUGGEST_ONLY'
    assert payload['model_name'] == 'GA_PERIODIZATION_BASELINE'
