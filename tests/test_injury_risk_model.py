from titan.science.injury_risk_model import InjuryRiskAssessment, InjuryRiskEnsembleModel


def test_low_risk_profile_returns_low_band():
    model = InjuryRiskEnsembleModel()
    assessment = model.assess_risk(
        {
            'hrv_delta': 1.0,
            'tsb': -2.0,
            'sleep_hours': 8.0,
            'soreness': 1.0,
            'acute_load_ratio': 1.0,
            'monotony': 1.1,
        }
    )

    assert isinstance(assessment, InjuryRiskAssessment)
    assert assessment.risk_band == 'LOW'
    assert assessment.mode == 'ADVISORY'


def test_high_risk_profile_returns_high_band():
    model = InjuryRiskEnsembleModel()
    assessment = model.assess_risk(
        {
            'hrv_delta': -12.0,
            'tsb': -28.0,
            'sleep_hours': 5.5,
            'soreness': 8.0,
            'acute_load_ratio': 1.6,
            'monotony': 2.0,
        }
    )

    assert assessment.risk_band == 'HIGH'
    assert assessment.risk_score >= 0.67


def test_assessment_dict_contract_is_stable():
    model = InjuryRiskEnsembleModel()
    assessment = model.assess_risk({})

    payload = model.as_dict(assessment)

    assert set(payload) == {
        'risk_score',
        'risk_band',
        'model_name',
        'mode',
        'recall_target',
        'evidence_label',
        'explainability',
    }
    assert payload['explainability']['plain_text_reason']
    assert payload['model_name'] == 'HEURISTIC_RISK_PROXY_v1'
    assert payload['mode'] == 'ADVISORY'
    assert payload['recall_target'] == 0.80
