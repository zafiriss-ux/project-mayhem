import pytest

from titan.science.automated_periodization import AutomatedPeriodizationEngine
from titan.science.injury_risk_model import InjuryRiskEnsembleModel
from titan.science.load_prediction_shadow import LoadPredictionShadowModel


@pytest.mark.parametrize(
    'env_value,enabled',
    [
        ('1', True),
        ('true', True),
        ('ON', True),
        ('0', False),
        ('false', False),
        ('off', False),
    ],
)
def test_kill_switch_env_controls_blocking(monkeypatch, env_value, enabled):
    monkeypatch.setenv('TITAN_ML_KILL_SWITCH', env_value)
    model = LoadPredictionShadowModel()

    if enabled:
        with pytest.raises(RuntimeError):
            model.predict_7d_load([100, 120], athlete_facing=True)
    else:
        pred = model.predict_7d_load([100, 120], athlete_facing=True)
        assert pred.predicted_load_7d > 0


def test_kill_switch_default_is_safe_on(monkeypatch):
    monkeypatch.delenv('TITAN_ML_KILL_SWITCH', raising=False)

    with pytest.raises(RuntimeError):
        InjuryRiskEnsembleModel().assess_risk({}, athlete_facing=True)


def test_non_athlete_facing_paths_remain_available(monkeypatch):
    monkeypatch.setenv('TITAN_ML_KILL_SWITCH', '1')

    load_prediction = LoadPredictionShadowModel().predict_7d_load([50, 60, 70])
    risk = InjuryRiskEnsembleModel().assess_risk({})
    suggestion = AutomatedPeriodizationEngine().suggest({})

    assert load_prediction.mode == 'SHADOW'
    assert risk.mode == 'ADVISORY'
    assert suggestion.mode == 'SUGGEST_ONLY'
