from titan.science.load_prediction_shadow import (
    LoadPredictionShadowModel,
    ShadowLoadPrediction,
)


def test_empty_input_returns_flat_zero_prediction():
    model = LoadPredictionShadowModel()
    pred = model.predict_7d_load([])

    assert isinstance(pred, ShadowLoadPrediction)
    assert pred.predicted_load_7d == 0.0
    assert pred.trend == 'FLAT'
    assert pred.mode == 'SHADOW'


def test_positive_growth_series_trends_up():
    model = LoadPredictionShadowModel(alpha=0.5)
    pred = model.predict_7d_load([100, 120, 140, 160, 180])

    assert pred.predicted_load_7d > 0
    assert pred.trend == 'UP'


def test_descending_series_trends_down():
    model = LoadPredictionShadowModel(alpha=0.5)
    pred = model.predict_7d_load([300, 200, 100, 50, 20])

    assert pred.trend == 'DOWN'


def test_as_dict_has_stable_contract_keys():
    model = LoadPredictionShadowModel()
    pred = model.predict_7d_load([50, 50, 50, 50])
    payload = model.as_dict(pred)

    assert set(payload) == {'predicted_load_7d', 'trend', 'model_name', 'mode'}
    assert payload['mode'] == 'SHADOW'
